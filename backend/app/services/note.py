import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Tuple, Union, Any

from fastapi import HTTPException
from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.douyin_downloader import DouyinDownloader
from app.downloaders.local_downloader import LocalDownloader
from app.downloaders.youtube_downloader import YoutubeDownloader
from app.db.video_task_dao import delete_task_by_video, insert_video_task
from app.enmus.exception import NoteErrorEnum, ProviderErrorEnum
from app.enmus.task_status_enums import (
    TaskStage,
    TaskStatus,
    global_progress,
    normalize_progress,
    stage_for_status,
    stage_label,
)
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.exceptions.provider import ProviderError
from app.gpt.base import GPT
from app.gpt.gpt_factory import GPTFactory
from app.models.audio_model import AudioDownloadResult
from app.models.gpt_model import GPTSource
from app.models.model_config import ModelConfig
from app.models.notes_model import AudioDownloadResult, NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.constant import SUPPORT_PLATFORM_MAP
from app.services.provider import ProviderService
from app.transcriber.base import Transcriber
from app.transcriber.transcriber_provider import get_transcriber, _transcribers
from app.utils.note_helper import replace_content_markers, prepend_source_link
from app.utils.logger import get_logger
from app.utils.screenshot_marker import extract_screenshot_timestamps
from app.utils.status_code import StatusCode
from app.utils.transcript_helper import densify_segments
from app.utils.video_helper import generate_screenshot
from app.utils.video_reader import VideoReader

# ------------------ 环境变量与全局配置 ------------------

# 从 .env 文件中加载环境变量
load_dotenv()

# 后端 API 地址与端口（若有需要可以在代码其他部分使用 BACKEND_BASE_URL）
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8483")
BACKEND_BASE_URL = f"{API_BASE_URL}:{BACKEND_PORT}"

# 输出目录（用于缓存音频、转写、Markdown 文件，以及存储截图）
NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))
NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_OUTPUT_DIR = os.getenv("OUT_DIR", "./static/screenshots")
# 图片基础 URL（用于生成 Markdown 中的图片链接，需前端静态目录对应）
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL", "/static/screenshots")

# 日志配置：统一走 app.utils.logger，保证控制台与 logs/app.log 双写、
# 并且带 `时间 [级别] 模块名 -` 前缀（裸 logging.getLogger 会因为无 handler 丢掉全部 INFO）。
logger = get_logger(__name__)


class NoteGenerator:
    """
    NoteGenerator 用于执行视频/音频下载、转写、GPT 生成笔记、插入截图/链接、
    以及将任务信息写入状态文件与数据库等功能。
    """

    def __init__(self):
        from app.services.transcriber_config_manager import TranscriberConfigManager
        config_manager = TranscriberConfigManager()
        self.model_size: str = config_manager.get_whisper_model_size()
        self.device: Optional[str] = None
        self.transcriber_type: str = config_manager.get_transcriber_type()
        self.transcriber: Transcriber = self._init_transcriber()
        self.video_path: Optional[Path] = None
        self.video_img_urls=[]
        # 429/鉴权等错误不应触发任务级重试，否则会重复下载和切片。
        self.last_error_non_retryable = False

        logger.info("NoteGenerator 初始化完成")


    # ---------------- 公有方法 ----------------

    def generate(
        self,
        video_url: Union[str, HttpUrl],
        platform: str,
        quality: DownloadQuality = DownloadQuality.medium,
        task_id: Optional[str] = None,
        model_name: Optional[str] = None,
        provider_id: Optional[str] = None,
        link: bool = False,
        screenshot: bool = False,
        _format: Optional[List[str]] = None,
        style: Optional[str] = None,
        extras: Optional[str] = None,
        output_path: Optional[str] = None,
        video_understanding: bool = False,
        video_interval: int = 0,
        grid_size: Optional[List[int]] = None,
        sampling_mode: str = "interval",
        max_frames: int = 60,
        frames_per_second: int = 2,
        frame_limit_mode: str = "total",
    ) -> NoteResult | None:
        """
        主流程：按步骤依次下载、转写、GPT 总结、截图/链接处理、存库、返回 NoteResult。

        :param video_url: 视频或音频链接
        :param platform: 平台名称，对应 SUPPORT_PLATFORM_MAP 中的键
        :param quality: 下载音频的质量枚举
        :param task_id: 用于标识本次任务的唯一 ID，亦用于状态文件和缓存文件命名
        :param model_name: GPT 模型名称
        :param provider_id: 模型供应商 ID
        :param link: 是否在笔记中插入视频片段链接
        :param screenshot: 是否在笔记中替换 Screenshot 标记为图片
        :param _format: 包含 'link' 或 'screenshot' 等字符串的列表，决定后续处理
        :param style: GPT 生成笔记的风格
        :param extras: 额外参数，传递给 GPT
        :param output_path: 下载输出目录（可选）
        :param video_understanding: 是否需要视频拼图理解（生成缩略图）
        :param video_interval: 视频帧截取间隔（秒），仅在 video_understanding 为 True 时生效
        :param grid_size: 生成缩略图时的网格大小，如 [3, 3]
        :param sampling_mode: interval=固定间隔抽帧；smart=高价值帧采样
        :param max_frames: smart 模式下单个视频的最大抽帧数（批量时每个视频各自的上限）
        :param frames_per_second: smart 模式下每秒最多保留的候选帧数
        :param frame_limit_mode: smart 限制方式二选一：total=只用 max_frames；per_second=只用 frames_per_second
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            self.last_error_non_retryable = False

            logger.info(f"开始生成笔记 (task_id={task_id})")
            self._update_status(task_id, TaskStatus.PARSING)

            # 获取下载器与 GPT 实例

            downloader = self._get_downloader(platform)
            gpt = self._get_gpt(model_name, provider_id)

            # 缓存文件路径
            audio_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_audio.json"
            transcript_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_transcript.json"
            markdown_cache_file = NOTE_OUTPUT_DIR / f"{task_id}_markdown.md"
            # 1. 获取字幕/转写：优先缓存 → 平台字幕 → 音频转写
            transcript = None

            # 尝试读取缓存
            if transcript_cache_file.exists():
                logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
                try:
                    data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                    segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
                    transcript = TranscriptResult(
                        language=data.get("language"),
                        full_text=data["full_text"],
                        segments=segments,
                    )
                    logger.info(f"已从缓存加载转写结果，共 {len(segments)} 段")
                except Exception as e:
                    logger.warning(f"加载转写缓存失败: {e}")

            # 缓存没有，尝试获取平台字幕
            if transcript is None:
                self._update_status(
                    task_id,
                    TaskStatus.PARSING,
                    message="正在获取平台字幕",
                    stage=TaskStage.FETCHING_SUBTITLES,
                )
                logger.info("尝试获取平台字幕（优先于音频下载）...")
                try:
                    transcript = downloader.download_subtitles(video_url)
                    if transcript and transcript.segments:
                        logger.info(f"成功获取平台字幕，共 {len(transcript.segments)} 段")
                        transcript_cache_file.write_text(
                            json.dumps(asdict(transcript), ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    else:
                        transcript = None
                        logger.info("平台无可用字幕，将下载音频后转写")
                except Exception as e:
                    logger.warning(f"获取平台字幕失败: {e}，将下载音频后转写")
                    transcript = None

            # 2. 下载音频/视频
            # 有字幕时只提取元信息，不下载音视频文件（除非需要截图/视频理解）
            has_transcript = transcript is not None
            need_full_download = not has_transcript or screenshot or video_understanding
            audio_meta = self._download_media(
                downloader=downloader,
                video_url=video_url,
                quality=quality,
                audio_cache_file=audio_cache_file,
                status_phase=TaskStatus.DOWNLOADING,
                platform=platform,
                output_path=output_path,
                screenshot=screenshot,
                video_understanding=video_understanding,
                video_interval=video_interval,
                grid_size=grid_size,
                skip_download=not need_full_download,
                sampling_mode=sampling_mode,
                frames_per_second=frames_per_second,
                frame_limit_mode=frame_limit_mode,
                task_id=task_id,
            )

            # 3. 如果前面没拿到字幕，走转写流程
            if transcript is None:
                transcript = self._get_transcript(
                    downloader=downloader,
                    video_url=video_url,
                    audio_file=audio_meta.file_path,
                    transcript_cache_file=transcript_cache_file,
                    status_phase=TaskStatus.TRANSCRIBING,
                    task_id=task_id,
                    # 上面已经探测过一次平台字幕，这里不再重复请求。
                    subtitle_attempted=True,
                )

            # spec 002：smart / hybrid 采样需要字幕，因此在转写完成后抽帧拼图
            if video_understanding and sampling_mode in ("smart", "hybrid") and self.video_path and grid_size:
                try:
                    frame_interval = video_interval if video_interval and video_interval > 0 else 6
                    # 部分 ASR（如 MiMo chat 风格）只返回整段文字、没有逐句时间轴，
                    # 这里按标点 + 字数比例插值出近似时间轴，供采样和 LLM 选帧使用。
                    plan_segments = densify_segments(
                        transcript.segments if transcript else []
                    )
                    subtitle_starts = [seg.start for seg in plan_segments]
                    llm_timestamps = []
                    self._update_status(
                        task_id,
                        TaskStatus.DOWNLOADING,
                        stage=TaskStage.PLANNING_FRAMES,
                        message=f"正在规划采样时间点，共 {len(subtitle_starts)} 个字幕分段",
                        detail={"subtitle_segments": len(subtitle_starts), "mode": sampling_mode},
                    )
                    if sampling_mode == "hybrid":
                        logger.info(f"综合采样：字幕分段 {len(subtitle_starts)} 个")
                        llm_timestamps = self._plan_frames_with_llm(
                            gpt, plan_segments, self.video_path, max_frames
                        )
                    else:
                        logger.info(f"高价值帧采样：字幕分段 {len(subtitle_starts)} 个")
                    self.video_img_urls = VideoReader(
                        video_path=str(self.video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=frame_interval,
                        unit_width=960,
                        unit_height=540,
                        save_quality=80,
                        sampling_mode=sampling_mode,
                        max_frames=max_frames,
                        frames_per_second=frames_per_second,
                        frame_limit_mode=frame_limit_mode,
                        subtitle_starts=subtitle_starts,
                        llm_timestamps=llm_timestamps,
                        progress_callback=self._video_progress_callback(task_id),
                    ).run()
                except Exception as exc:
                    logger.error(f"视频理解抽帧失败：{exc}")
                    self._handle_exception(task_id, exc)
                    raise

            # 3. GPT 总结
            markdown = self._summarize_text(
                audio_meta=audio_meta,
                transcript=transcript,
                gpt=gpt,
                markdown_cache_file=markdown_cache_file,
                link=link,
                screenshot=screenshot,
                formats=_format or [],
                style=style,
                extras=extras,
                video_img_urls=self.video_img_urls,
                task_id=task_id,
            )

            # 4. 截图 & 链接替换
            if _format:
                self._update_status(
                    task_id,
                    TaskStatus.FORMATTING,
                    stage=TaskStage.POST_PROCESSING,
                    message="正在整理截图和视频链接",
                    stage_progress=0,
                    detail={"formats": _format},
                )
                markdown = self._post_process_markdown(
                    markdown=markdown,
                    video_path=self.video_path,
                    formats=_format,
                    audio_meta=audio_meta,
                    platform=platform,
                    task_id=task_id,
                )

            markdown = prepend_source_link(markdown, str(video_url))

            # 5. 保存记录到数据库
            self._update_status(
                task_id,
                TaskStatus.SAVING,
                stage=TaskStage.SAVING,
                message="正在保存笔记和任务记录",
                stage_progress=10,
                detail={"step": "save_metadata"},
            )
            self._save_metadata(video_id=audio_meta.video_id, platform=platform, task_id=task_id)

            # 6. 完成
            self._update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"笔记生成成功 (task_id={task_id})")
            return NoteResult(markdown=markdown, transcript=transcript, audio_meta=audio_meta)

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            self._update_status(task_id, TaskStatus.FAILED, message=str(exc))
            self.last_error_non_retryable = bool(getattr(exc, "non_retryable", False))

            return None

    @staticmethod
    def delete_note(video_id: str, platform: str) -> int:
        """
        删除数据库中对应 video_id 与 platform 的任务记录

        :param video_id: 视频 ID
        :param platform: 平台标识
        :return: 删除的记录数
        """
        logger.info(f"删除笔记记录 (video_id={video_id}, platform={platform})")
        return delete_task_by_video(video_id, platform)

    # ---------------- 私有方法 ----------------

    def _plan_frames_with_llm(self, gpt, segments, video_path, max_frames) -> list:
        """综合采样：让 LLM 读字幕挑出值得截图的时间点。

        LLM 不可用 / 调用失败 / 没有字幕时返回 []，综合采样自动退回
        「高价值 + 均匀」两路，不影响任务本身。
        """
        if not segments:
            logger.info("综合采样：没有字幕分段，跳过 LLM 选帧")
            return []
        if not hasattr(gpt, "plan_frame_timestamps"):
            logger.warning("当前模型客户端不支持 LLM 选帧，综合采样退回高价值 + 均匀")
            return []
        try:
            from app.utils.audio_helper import probe_duration_seconds
            from app.utils.frame_sampler import HYBRID_LLM_RATIO

            duration = probe_duration_seconds(video_path)
            max_items = max(1, int(max_frames * HYBRID_LLM_RATIO))
            picks = gpt.plan_frame_timestamps(
                segments, duration=duration, max_items=max_items
            )
            logger.info(f"综合采样：LLM 选中 {len(picks)} 个截图时间点")
            return picks
        except Exception as exc:  # noqa: BLE001 - 选帧失败不应让整个任务失败
            logger.warning(f"LLM 选帧失败，退回高价值 + 均匀采样：{exc}", exc_info=True)
            return []

    def _init_transcriber(self) -> Transcriber:
        """
        根据环境变量 TRANSCRIBER_TYPE 动态获取并实例化转写器
        """
        if self.transcriber_type not in _transcribers:
            logger.error(f"未找到支持的转写器：{self.transcriber_type}")
            raise Exception(f"不支持的转写器：{self.transcriber_type}")

        logger.info(f"使用转写器：{self.transcriber_type}")

        transcriber_options = None
        if self.transcriber_type == "openai-asr":
            # OpenAI 兼容 ASR 的端点配置在「音频转写配置」页维护，取当前选中的那条
            from app.services.transcriber_config_manager import TranscriberConfigManager
            endpoint = TranscriberConfigManager().get_active_openai_asr()
            if not endpoint:
                raise Exception(
                    "尚未配置 OpenAI 兼容 ASR，请先在「设置 → 音频转写配置」添加并选择"
                )
            transcriber_options = endpoint

        return get_transcriber(
            transcriber_type=self.transcriber_type,
            model_size=self.model_size,
            transcriber_options=transcriber_options,
        )

    def _get_gpt(self, model_name: Optional[str], provider_id: Optional[str]) -> GPT:
        """
        根据 provider_id 获取对应的 GPT 实例
        :param model_name: GPT 模型名称
        :param provider_id: 供应商 ID
        :return: GPT 实例
        """
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            logger.error(f"[get_gpt] 未找到模型供应商: provider_id={provider_id}")
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND,message=ProviderErrorEnum.NOT_FOUND.message)
        logger.info(f"创建 GPT 实例 {provider_id}")
        config = ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model_name=model_name,
            provider=provider["type"],
            name=provider["name"],
        )
        return GPTFactory().from_config(config)

    def _get_downloader(self, platform: str) -> Downloader:
        """
        根据平台名称获取对应的下载器实例

        :param platform: 平台标识，需在 SUPPORT_PLATFORM_MAP 中
        :return: 对应的 Downloader 子类实例
        """
        downloader_cls = SUPPORT_PLATFORM_MAP.get(platform)
        logger.debug(f"实例化下载器 -  {platform}")
        instance = None
        if not downloader_cls:
            logger.error(f"不支持的平台：{platform}")
            raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                            message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)
        try:
            instance = downloader_cls
        except Exception as e:
            logger.error(f"实例化下载器失败：{e}")


        logger.info(f"使用下载器：{downloader_cls.__class__}")
        return instance

    def _update_status(
        self,
        task_id: Optional[str],
        status: Union[str, TaskStatus],
        message: Optional[str] = None,
        *,
        stage: Optional[TaskStage | str] = None,
        progress: Optional[float] = None,
        stage_progress: Optional[float] = None,
        detail: Optional[dict] = None,
    ):
        """Write a backward-compatible task status with optional stage metadata."""
        if not task_id:
            return

        NOTE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        status_file = NOTE_OUTPUT_DIR / f"{task_id}.status.json"
        status_value = status.value if isinstance(status, TaskStatus) else str(status)
        resolved_stage = stage or stage_for_status(status_value)
        try:
            resolved_stage = TaskStage(resolved_stage)
        except (TypeError, ValueError):
            resolved_stage = stage_for_status(status_value)

        normalized_stage_progress = normalize_progress(stage_progress)
        normalized_progress = normalize_progress(progress)
        if normalized_progress is None:
            normalized_progress = global_progress(resolved_stage, normalized_stage_progress)

        data = {
            "status": status_value,
            "stage": resolved_stage.value,
            "stage_label": stage_label(resolved_stage),
            "progress": normalized_progress,
            "stage_progress": normalized_stage_progress,
            "message": message or "",
            "detail": detail or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Keep a unique temporary file so concurrent writes cannot collide.
            temp_file = status_file.with_name(f"{status_file.name}.{uuid.uuid4().hex[:8]}.tmp")
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_file.replace(status_file)
        except Exception as e:
            logger.error(f"写入状态文件失败 (task_id={task_id})：{e}")
            try:
                with status_file.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                logger.exception("写入状态文件兜底失败 (task_id=%s)", task_id)

    def _handle_exception(self, task_id, exc):
        logger.error(f"任务异常 (task_id={task_id})", exc_info=True)
        error_message = getattr(exc, 'detail', str(exc))
        if isinstance(error_message, dict):
            try:
                error_message = json.dumps(error_message, ensure_ascii=False)
            except:
                error_message = str(error_message)
        self._update_status(task_id, TaskStatus.FAILED, message=error_message)

    def _video_progress_callback(self, task_id: str):
        def report(stage: str, current=None, total=None, message: str = ""):
            stage_progress = None
            if current is not None and total:
                stage_progress = current / total * 100
            self._update_status(
                task_id,
                TaskStatus.DOWNLOADING,
                message=message,
                stage=stage,
                stage_progress=stage_progress,
                detail={"current": current, "total": total, "unit": "frames" if "frame" in stage else "grids"},
            )

        return report

    def _transcriber_progress_callback(self, task_id: str):
        """把逐段转写进度写回任务状态，供日志和前端进度条使用。"""

        def report(current, total, message: str = ""):
            stage_progress = None
            if current is not None and total:
                stage_progress = current / total * 100
            self._update_status(
                task_id,
                TaskStatus.TRANSCRIBING,
                message=message or f"正在转写 {current}/{total}",
                stage=TaskStage.TRANSCRIBING,
                stage_progress=stage_progress,
                detail={"current": current, "total": total, "unit": "segments"},
            )

        return report


    def _download_media(
        self,
        downloader: Downloader,
        video_url: Union[str, HttpUrl],
        quality: DownloadQuality,
        audio_cache_file: Path,
        status_phase: TaskStatus,
        platform: str,
        output_path: Optional[str],
        screenshot: bool,
        video_understanding: bool,
        video_interval: int,
        grid_size: List[int],
        skip_download: bool = False,
        sampling_mode: str = "interval",
        frames_per_second: int = 2,
        frame_limit_mode: str = "total",
        task_id: Optional[str] = None,
    ) -> AudioDownloadResult | None:
        """
        1. 检查音频缓存；若不存在，则根据需要下载音频或视频（若需截图/可视化）。
        2. 如果需要视频，则先下载视频并生成缩略图集，再下载音频。
        3. 返回 AudioDownloadResult

        :param downloader: Downloader 实例
        :param video_url: 视频/音频链接
        :param quality: 音频下载质量
        :param audio_cache_file: 本地缓存 JSON 文件路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.DOWNLOADING
        :param platform: 平台标识
        :param output_path: 下载输出目录（可为 None）
        :param screenshot: 是否需要在笔记中插入截图
        :param video_understanding: 是否需要生成缩略图
        :param video_interval: 视频截帧间隔
        :param grid_size: 缩略图网格尺寸
        :param task_id: 任务 ID（由调用方显式传入，不再从缓存文件名反推，避免写错状态文件）
        :return: AudioDownloadResult 对象
        """
        self._update_status(task_id, status_phase, stage=TaskStage.DOWNLOADING_AUDIO, message="准备下载音频")

        # 已有缓存，尝试加载
        if audio_cache_file.exists():
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                data = json.loads(audio_cache_file.read_text(encoding="utf-8"))
                return AudioDownloadResult(**data)
            except Exception as e:
                logger.warning(f"读取音频缓存失败，将重新下载：{e}")

        # 有字幕且不需要截图/视频理解时，只提取元信息不下载文件
        if skip_download:
            logger.info("已有字幕，仅提取视频元信息（不下载音视频）")
            try:
                audio = downloader.download(
                    video_url=video_url,
                    quality=quality,
                    output_dir=output_path,
                    need_video=False,
                    skip_download=True,
                )
                audio_cache_file.write_text(
                    json.dumps(asdict(audio), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"元信息提取完成 ({audio_cache_file})")
                return audio
            except Exception as exc:
                logger.warning(f"元信息提取失败，将尝试完整下载: {exc}")

        # 判断是否需要下载视频
        need_video = screenshot or video_understanding
        if screenshot and not grid_size:
            grid_size = [2, 2]

        frame_interval = video_interval if video_interval and video_interval > 0 else 6
        if need_video:
            try:
                self._update_status(
                    task_id,
                    TaskStatus.DOWNLOADING,
                    stage=TaskStage.DOWNLOADING_VIDEO,
                    message="正在下载视频",
                )
                logger.info("开始下载视频")
                video_path_str = downloader.download_video(video_url)
                self.video_path = Path(video_path_str)
                logger.info(f"视频下载完成：{self.video_path}")

                if grid_size and sampling_mode not in ("smart", "hybrid"):
                    self._update_status(
                        task_id,
                        TaskStatus.DOWNLOADING,
                        message="正在抽取视频画面并拼接网格图",
                        stage=TaskStage.EXTRACTING_FRAMES,
                    )
                    self.video_img_urls = VideoReader(
                        video_path=str(self.video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=frame_interval,
                        unit_width=960,
                        unit_height=540,
                        save_quality=80,
                        progress_callback=self._video_progress_callback(task_id),
                    ).run()
                elif grid_size:
                    logger.info("smart 采样需要字幕，抽帧将在转写完成后进行")
                else:
                    logger.info("未指定 grid_size，跳过缩略图生成")
            except Exception as exc:
                logger.error(f"视频下载失败：{exc}")
                self._handle_exception(task_id, exc)
                raise

        # 下载音频
        try:
            self._update_status(
                task_id,
                TaskStatus.DOWNLOADING,
                stage=TaskStage.DOWNLOADING_AUDIO,
                message="正在下载音频",
            )
            logger.info("开始下载音频")
            audio = downloader.download(
                video_url=video_url,
                quality=quality,
                output_dir=output_path,
                need_video=need_video,
            )
            audio_cache_file.write_text(json.dumps(asdict(audio), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"音频下载并缓存成功 ({audio_cache_file})")
            return audio
        except Exception as exc:
            logger.error(f"音频下载失败：{exc}")
            self._handle_exception(task_id, exc)
            raise


    def _get_transcript(
        self,
        downloader: Downloader,
        video_url: str,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
        task_id: Optional[str] = None,
        subtitle_attempted: bool = False,
    ) -> TranscriptResult | None:
        """
        优先获取平台字幕，没有则 fallback 到音频转写

        :param downloader: 下载器实例
        :param video_url: 视频链接
        :param audio_file: 音频文件路径（用于 fallback 转写）
        :param transcript_cache_file: 缓存文件路径
        :param status_phase: 状态枚举
        :param task_id: 任务 ID
        :param subtitle_attempted: 调用方是否已经探测过平台字幕（避免重复网络请求）
        :return: TranscriptResult 对象
        """
        self._update_status(task_id, status_phase)

        # 已有缓存，直接返回
        if transcript_cache_file.exists():
            logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
                return TranscriptResult(language=data.get("language"), full_text=data["full_text"], segments=segments)
            except Exception as e:
                logger.warning(f"加载转写缓存失败，将重新获取：{e}")

        # 1. 先尝试获取平台字幕（调用方已试过时跳过，避免重复请求）
        if subtitle_attempted:
            logger.info("平台字幕已探测过（无可用字幕），跳过重复请求")
        else:
            logger.info("尝试获取平台字幕...")
            try:
                transcript = downloader.download_subtitles(video_url)
                if transcript and transcript.segments:
                    logger.info(f"成功获取平台字幕，共 {len(transcript.segments)} 段")
                    # 缓存结果
                    transcript_cache_file.write_text(
                        json.dumps(asdict(transcript), ensure_ascii=False, indent=2),
                        encoding="utf-8"
                    )
                    return transcript
                else:
                    logger.info("平台无可用字幕，将使用音频转写")
            except Exception as e:
                logger.warning(f"获取平台字幕失败: {e}，将使用音频转写")

        # 2. Fallback 到音频转写
        self._update_status(
            task_id,
            TaskStatus.TRANSCRIBING,
            stage=TaskStage.TRANSCRIBING,
            message="平台无可用字幕，开始音频转写",
        )
        return self._transcribe_audio(
            audio_file=audio_file,
            transcript_cache_file=transcript_cache_file,
            status_phase=status_phase,
            task_id=task_id,
        )

    def _transcribe_audio(
        self,
        audio_file: str,
        transcript_cache_file: Path,
        status_phase: TaskStatus,
        task_id: Optional[str] = None,
    ) -> TranscriptResult | None:
        """
        1. 检查转写缓存；若存在则尝试加载，否则调用转写器生成并缓存。
        2. 返回 TranscriptResult 对象

        :param audio_file: 音频文件本地路径
        :param transcript_cache_file: 转写结果缓存路径
        :param status_phase: 对应的状态枚举，如 TaskStatus.TRANSCRIBING
        :param task_id: 任务 ID（由调用方传入，不再从文件名反推）
        :return: TranscriptResult 对象
        """
        self._update_status(task_id, status_phase)

        # 已有缓存，尝试加载
        if transcript_cache_file.exists():
            logger.info(f"检测到转写缓存 ({transcript_cache_file})，尝试读取")
            try:
                data = json.loads(transcript_cache_file.read_text(encoding="utf-8"))
                segments = [TranscriptSegment(**seg) for seg in data.get("segments", [])]
                return TranscriptResult(language=data["language"], full_text=data["full_text"], segments=segments)
            except Exception as e:
                logger.warning(f"加载转写缓存失败，将重新转写：{e}")

        # 调用转写器
        try:
            logger.info("开始转写音频")
            # 转写器是单例：必须在调用前安装回调，调用后复原，
            # 否则进度回调要么收不到、要么把上一个任务的 task_id 带到下一个任务。
            had_callback = hasattr(self.transcriber, "progress_callback")
            previous_callback = getattr(self.transcriber, "progress_callback", None)
            setattr(
                self.transcriber,
                "progress_callback",
                self._transcriber_progress_callback(task_id),
            )
            try:
                transcript = self.transcriber.transcript(file_path=audio_file)
            finally:
                if had_callback:
                    setattr(self.transcriber, "progress_callback", previous_callback)
                else:
                    try:
                        delattr(self.transcriber, "progress_callback")
                    except AttributeError:
                        pass

            transcript_cache_file.write_text(json.dumps(asdict(transcript), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"转写并缓存成功 ({transcript_cache_file})")
            return transcript
        except Exception as exc:
            logger.error(f"音频转写失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

    def _summarize_text(
        self,
        audio_meta: AudioDownloadResult,
        transcript: TranscriptResult,
        gpt: GPT,
        markdown_cache_file: Path,
        link: bool,
        screenshot: bool,
        formats: List[str],
        style: Optional[str],
        extras: Optional[str],
            video_img_urls: List[str],
        task_id: Optional[str] = None,
    ) -> str | None:
        """
        调用 GPT 对转写结果进行总结，生成 Markdown 文本并缓存。

        :param audio_meta: AudioDownloadResult 元信息
        :param transcript: TranscriptResult 转写结果
        :param gpt: GPT 实例
        :param markdown_cache_file: Markdown 缓存路径
        :param link: 是否在笔记中插入链接
        :param screenshot: 是否在笔记中生成截图占位
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param style: GPT 输出风格
        :param extras: GPT 额外参数
        :param task_id: 真实任务 ID（用于状态文件与 checkpoint key）
        :return: 生成的 Markdown 字符串
        """
        self._update_status(
            task_id,
            TaskStatus.SUMMARIZING,
            stage=TaskStage.SUMMARIZING,
            message=f"正在调用模型生成笔记（{len(transcript.segments) if transcript else 0} 段字幕）",
            detail={
                "title": audio_meta.title,
                "segments": len(transcript.segments) if transcript else 0,
                "video_images": len(video_img_urls or []),
            },
        )

        source = GPTSource(
            title=audio_meta.title,
            segment=transcript.segments,
            tags=audio_meta.raw_info.get("tags", []),
            screenshot=screenshot,
            video_img_urls=video_img_urls,
            link=link,
            _format=formats,
            style=style,
            extras=extras,
            checkpoint_key=task_id,
        )

        try:
            markdown = gpt.summarize(source)
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            logger.info(f"GPT 总结并缓存成功 ({markdown_cache_file})")
            return markdown
        except Exception as exc:
            logger.error(f"GPT 总结失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

    def _post_process_markdown(
        self,
        markdown: str,
        video_path: Optional[Path],
        formats: List[str],
        audio_meta: AudioDownloadResult,
        platform: str,
        task_id: Optional[str] = None,
    ) -> str:
        """
        对生成的 Markdown 做后期处理：插入截图和/或插入链接。

        :param markdown: 原始 Markdown 字符串
        :param video_path: 本地视频路径（可为 None）
        :param formats: 包含 'link' 或 'screenshot' 的列表
        :param audio_meta: AudioDownloadResult 元信息，用于链接替换
        :param platform: 平台标识，用于链接替换
        :param task_id: 任务 ID（用于阶段进度回报）
        :return: 处理后的 Markdown 字符串
        """
        if "screenshot" in formats and video_path:
            try:
                markdown = self._insert_screenshots(markdown, video_path, task_id=task_id)
            except Exception as exc:
                logger.warning("截图插入失败，跳过该步骤")

        if "link" in formats:
            try:
                markdown = replace_content_markers(markdown, video_id=audio_meta.video_id, platform=platform)
            except Exception as e:
                logger.warning(f"链接插入失败，跳过该步骤：{e}")

        self._update_status(
            task_id,
            TaskStatus.FORMATTING,
            stage=TaskStage.POST_PROCESSING,
            message="截图与链接处理完成",
            stage_progress=100,
        )
        return markdown

    def _insert_screenshots(
        self,
        markdown: str,
        video_path: Path,
        task_id: Optional[str] = None,
    ) -> str | None | Any:
        """
        扫描 Markdown 文本中所有 Screenshot 标记，并替换为实际生成的截图链接。

        截图由 ffmpeg 逐标记生成，属于纯等待型工作，因此并发执行；
        结果按标记出现顺序回填，保证 URL 顺序与替换位置不变。

        :param markdown: 含有 *Screenshot-mm:ss 或 Screenshot-[mm:ss] 标记的 Markdown 文本
        :param video_path: 本地视频文件路径
        :param task_id: 任务 ID（用于阶段进度回报）
        :return: 替换后的 Markdown 字符串
        """
        matches: List[Tuple[str, int]] = extract_screenshot_timestamps(markdown)
        if not matches:
            return markdown

        total = len(matches)
        self._update_status(
            task_id,
            TaskStatus.FORMATTING,
            stage=TaskStage.POST_PROCESSING,
            message=f"正在生成 {total} 张截图",
            stage_progress=0,
            detail={"current": 0, "total": total, "unit": "screenshots"},
        )

        counter_lock = threading.Lock()
        completed = 0

        def _render(item: Tuple[int, Tuple[str, int]]) -> Tuple[str, str]:
            nonlocal completed
            idx, (marker, ts) = item
            img_path = generate_screenshot(str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx)
            filename = Path(img_path).name
            # 构建前端可访问的 URL，例如 /static/screenshots/{filename}
            img_url = f"{IMAGE_BASE_URL.rstrip('/')}/{filename}"
            with counter_lock:
                completed += 1
                current = completed
            self._update_status(
                task_id,
                TaskStatus.FORMATTING,
                stage=TaskStage.POST_PROCESSING,
                message=f"正在生成截图 {current}/{total}",
                stage_progress=current / total * 100,
                detail={"current": current, "total": total, "unit": "screenshots"},
            )
            return marker, img_url

        workers = max(1, min(8, os.cpu_count() or 4, total))
        try:
            if workers == 1:
                rendered = [_render(item) for item in enumerate(matches)]
            else:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="screenshot") as executor:
                    rendered = list(executor.map(_render, list(enumerate(matches))))
        except Exception as exc:
            logger.error(f"生成截图失败：{exc}")
            # self._handle_exception(task_id, exc)
            return None

        for marker, img_url in rendered:
            markdown = markdown.replace(marker, f"![]({img_url})", 1)
        return markdown

    @staticmethod
    def _extract_screenshot_timestamps(markdown: str) -> List[Tuple[str, int]]:
        """
        从 Markdown 文本中提取所有 '*Screenshot-mm:ss' 或 'Screenshot-[mm:ss]' 标记，
        返回 [(原始标记文本, 时间戳秒数), ...] 列表。

        :param markdown: 原始 Markdown 文本
        :return: 标记与对应时间戳秒数的列表
        """
        return extract_screenshot_timestamps(markdown)

    def _save_metadata(self, video_id: str, platform: str, task_id: str) -> None:
        """
        将生成的笔记任务记录插入数据库

        :param video_id: 视频 ID
        :param platform: 平台标识
        :param task_id: 任务 ID
        """
        try:
            insert_video_task(video_id=video_id, platform=platform, task_id=task_id)
            logger.info(f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})")
        except Exception as e:
            logger.error(f"保存任务记录失败：{e}")
