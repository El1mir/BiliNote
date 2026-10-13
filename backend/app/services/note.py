import base64
import json
import os
import re
import threading
import time
import uuid
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union, Any

from pydantic import HttpUrl
from dotenv import load_dotenv

from app.downloaders.base import Downloader
from app.db.video_task_dao import (
    delete_task_by_video,
    get_video_task,
    insert_video_task,
)
from app.db.note_group_dao import assign_task_to_group
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
from app.utils.llm_rate_limit import is_rate_limit_error
from app.utils.logger import get_logger
from app.utils.screenshot_marker import extract_screenshot_timestamps
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

# spec 008 ticket 02：OCR 辅助模式的插图占位符与文本比对工具



def _safe_float(value, default: float = 0.0) -> float:
    """把任意值转成 float；转不了就返回 default，绝不抛异常。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """把任意值转成 int；转不了就返回 default，绝不抛异常。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _match_candidate_frames(picked, candidates, tolerance: float | None = None) -> list:
    """把挑选层的时间点吸附到最近的候选帧上，返回真正存在的候选帧时间点。

    挑选层只看得到字幕（时间戳是小数，如 31.5 / 60.1），而 interval 采样抽出的
    候选帧落在整秒上。旧实现要求毫秒精确相等，于是模型挑中的点几乎全被丢弃
    （生产日志实测命中率 0/39、8/44、5/200），两次 LLM 调用等于白跑。

    容差缺省取「相邻候选帧间距的中位数 / 2」——正好是「最近邻」的语义边界：
    一个挑选点最多吸附到一个候选帧，且只吸附到比其它候选帧都更近的那一个。
    返回值一定是 candidates 里的元素，恒等式「候选帧 ⊇ 判定通过」不受影响。
    """
    ordered = sorted({round(_safe_float(t), 3) for t in (candidates or [])})
    if not ordered:
        return []

    if tolerance is None:
        if len(ordered) >= 2:
            gaps = sorted(b - a for a, b in zip(ordered, ordered[1:]))
            tolerance = gaps[len(gaps) // 2] / 2.0
        else:
            tolerance = 0.0
    tolerance = max(0.0, float(tolerance))

    matched = []
    seen = set()
    for raw in picked or []:
        target = round(_safe_float(raw), 3)
        nearest = min(ordered, key=lambda c: (abs(c - target), c))
        if abs(nearest - target) <= tolerance and nearest not in seen:
            seen.add(nearest)
            matched.append(nearest)
    return sorted(matched)


def _shot_marker_pattern(index: int) -> re.Pattern:
    """`[[SHOT-n]]` 占位符的正则。

    容忍模型写成 `[[shot - 1]]` 这类变形（大小写、空白、连字符都放过），
    但编号必须严格相等：`[[SHOT-1]]` 不能匹配到 `[[SHOT-11]]`。
    """
    return re.compile(
        r"\[\[\s*SHOT\s*-?\s*" + str(_safe_int(index)) + r"\s*\]\]", re.IGNORECASE
    )



def _serialize_ocr_result(result: Any) -> Any:
    """把 OcrResult 展开成可 JSON 化的纯 dict；非 dataclass 原样返回。

    OcrResult.blocks 是 OcrBlock 列表（dataclass），raw 是任意字典，
    两者都不能直接 json.dumps；这里只展一层 blocks，raw 交给 json 自己处理
    （它本来就是从 JSON 响应里取出来的）。
    """
    if not is_dataclass(result) or isinstance(result, type):
        return result
    payload = asdict(result)
    return payload


def _deserialize_ocr_result(value: Any) -> Any:
    """把 :func:`_serialize_ocr_result` 写出的 dict 还原回 OcrResult；失败返回 None。"""
    if not isinstance(value, dict):
        return value
    try:
        from app.services.ocr_client import OcrBlock, OcrResult

        blocks = [
            OcrBlock(**item) if isinstance(item, dict) else item
            for item in (value.get("blocks") or [])
        ]
        return OcrResult(
            markdown=str(value.get("markdown") or ""),
            blocks=blocks,
            raw=value.get("raw") or {},
            protocol=str(value.get("protocol") or ""),
            model_name=str(value.get("model_name") or ""),
        )
    except Exception:
        return None

def _normalize_for_compare(text: str) -> str:
    """只留文字、去掉空白与标点，用于判断 OCR 内容是否已经出现在正文里。"""
    return re.sub(r"[\s\W_]+", "", text or "").lower()


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
        self.video_img_urls = []
        # spec 008 ticket 02：OCR 辅助模式的状态。
        # 三者的语义是「None = 还没算过，可以复用上一轮的结果」——重试时不清空，
        # 见 generate() 里的 bug 2 注释。
        self.ocr_assist: bool = False  # OCR 层：是否把图上的文字搬进笔记
        # 判定层：挑选 + 判定要不要跑。开着「画面编入笔记」就必须判定，
        # 否则没有任何东西能保证「只有被判为值得的画面才插图」。
        # 它与 ocr_assist 是两件事——判定不需要部署 OCR 服务，OCR 才需要。
        self.ocr_judgement_enabled: bool = False
        self.ocr_cache_url: Optional[str] = None  # 上面这些结果属于哪个 video_url
        # 磁盘上的缓存是不是「OCR 关闭时」跑出来的：那种缓存只有判定结果、
        # 没有图上文字，这次开了 OCR 就不能直接复用。
        self.ocr_cache_used_ocr: bool = False
        self.frame_candidates: Optional[List[float]] = None  # 抽帧实际产出的时间点
        self.picked_frames: Optional[List[float]] = None  # 挑选层挑中的时间点
        self.approved_shots: Optional[list] = None  # 判定通过、必须编入笔记的截图点
        # 判定通过的每张图各自 OCR 出来的完整内容（m04445：无论 OCR 返回什么，
        # 都作为参考喂给总结模型）。键是时间点秒数，值是结构化参考 dict。
        self.ocr_texts: Optional[dict] = None
        # OCR 失败的张数。失败不致命（q4_ocr_failure=A：跳过该张、图照插），
        # 但必须计数并进日志，否则「参考内容静默缺失」永远看不出来。
        self.ocr_failures: int = 0
        # 判定通过的每张图的单独截图 data URL，顺序与 approved_shots 一致。
        # 送进总结模型的是**这一批单帧**，不再是网格图（q10/q11）。
        self.shot_image_urls: Optional[list] = None
        # 鉴权/参数等错误不应触发任务级重试，否则会重复下载和切片。
        self.last_error_non_retryable = False
        # 429 是**另一条路**（spec 012）：不是「不能重试」，而是「还没轮到」——
        # 交给任务级循环等全局冷却窗口，不判失败、不计熔断。
        self.last_error_rate_limited = False

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
        ocr_assist: Optional[bool] = None,
        # spec 007：任务所属分组。批量任务整批归入同一个组；单条任务为 None。
        group_id: Optional[str] = None,
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
        :param ocr_assist: 按任务覆盖 OCR 辅助开关；None=沿用全局设置（spec 008 ticket 02）
        :return: NoteResult 对象，包含 markdown 文本、转写结果和音频元信息
        """
        if grid_size is None:
            grid_size = []

        try:
            self.last_error_non_retryable = False
            self.last_error_rate_limited = False

            # spec 008 ticket 02：先决定走不走 OCR 辅助路径。放在最前面是为了让
            # 「启用了但没配好」立刻失败，而不是等下载转写完才报错。
            # 判定层永远开启：它决定「哪些画面值得编入笔记」，与 OCR 服务无关。
            # OCR 层按开关走（None=沿用全局设置），只影响「图上文字要不要搬进笔记」。
            self.ocr_judgement_enabled = True
            self.ocr_assist = self._resolve_ocr_assist(ocr_assist)
            self.group_id = group_id
            # bug 2 修复：重试时**不要**清空上一轮已经算出来的抽帧/挑选/判定结果。
            # `NoteGenerator` 实例建在重试循环之外，同一个实例会被反复 generate()，
            # 原先这里的无条件重置会让重试白扔掉几十分钟的抽帧与两次 LLM 调用。
            # 现在的语义：`None` = 还没算过，算过就复用；任务换 video_url 时才重置。
            if self.ocr_cache_url != str(video_url):
                self.ocr_cache_url = str(video_url)
                self.frame_candidates = None
                self.picked_frames = None
                self.approved_shots = None
            # 磁盘缓存是「进程重启后重试」的最后一道保险：内存里已经算过就不读，
            # 读到的缓存若来自降级运行（当时没开 OCR）而这次开了，也不能复用——
            # 那种缓存里没有图上文字，复用会把公式/表格降级成一张图。
            if self.ocr_assist or self.approved_shots is None:
                reused = self._load_ocr_cache(str(video_url), need_ocr=self.ocr_assist)
                logger.info(
                    "画面判定已启用：本次只把「判定值得编入笔记」的画面写进笔记%s",
                    "（复用上一轮已算好的抽帧与判定结果）" if reused else "",
                )

            logger.info(f"开始生成笔记 (task_id={task_id})")
            self._update_status(task_id, TaskStatus.PARSING)

            # 每个任务在执行时读取当前激活模型，排队任务也会同步使用新选择。
            from app.services.active_model import resolve_active_model

            active_model = resolve_active_model()
            model_name = active_model["model_name"]
            provider_id = active_model["provider_id"]

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
                    segments = [
                        TranscriptSegment(**seg) for seg in data.get("segments", [])
                    ]
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
                        logger.info(
                            f"成功获取平台字幕，共 {len(transcript.segments)} 段"
                        )
                        transcript_cache_file.write_text(
                            json.dumps(
                                asdict(transcript), ensure_ascii=False, indent=2
                            ),
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
            if (
                video_understanding
                and sampling_mode in ("smart", "hybrid")
                and self.video_path
                and grid_size
            ):
                try:
                    # 六层日志之「抽帧层」的计时起点。放在 try 开头是为了把
                    # densify_segments + LLM 选帧（hybrid）+ 抽帧拼图一起算进去，
                    # 这三步都是纯等待型工作，分开计时对定位瓶颈没有帮助。
                    frame_started = time.perf_counter()
                    frame_interval = (
                        video_interval if video_interval and video_interval > 0 else 6
                    )
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
                        detail={
                            "subtitle_segments": len(subtitle_starts),
                            "mode": sampling_mode,
                        },
                    )
                    if sampling_mode == "hybrid":
                        logger.info(f"综合采样：字幕分段 {len(subtitle_starts)} 个")
                        llm_timestamps = self._plan_frames_with_llm(
                            gpt, plan_segments, self.video_path, max_frames
                        )
                    else:
                        logger.info(f"高价值帧采样：字幕分段 {len(subtitle_starts)} 个")
                    reader = VideoReader(
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
                        task_id=task_id,
                    )
                    self.video_img_urls = reader.run()
                    # 候选帧 = 真正抽出来并进了网格图的时间点（spec 008 ticket 02）
                    self.frame_candidates = list(reader.candidate_timestamps)
                    # 六层日志之「抽帧层」（m02661 q5_log_layers=A）：候选帧数与耗时。
                    # 候选帧数是整条恒等式（候选帧 ⊇ 判定通过 ⊇ 实际插入）的左端，
                    # 它和网格图数量一起决定了挑选层与判定层的输入规模。
                    logger.info(
                        "OCR 辅助抽帧层：采样=%s 候选帧=%d 网格图=%d 耗时=%.3fs task_id=%s",
                        sampling_mode,
                        len(self.frame_candidates),
                        len(self.video_img_urls or []),
                        time.perf_counter() - frame_started,
                        task_id,
                    )
                except Exception as exc:
                    logger.error(f"视频理解抽帧失败：{exc}")
                    self._handle_exception(task_id, exc)
                    raise

            # 2.5 OCR 辅助：两次 LLM 调用，必须在总结之前完成，因为提示词里要给出
            # [[SHOT-n]] 对照表。顺序（m02661 q2_order=A）：
            #   挑选（只看字幕） → 判定值得（看网格图） → 对值得的帧逐张 OCR
            #   → 按 OCR 结果分流 → 完成。
            if self.ocr_judgement_enabled:
                if self.approved_shots is not None:
                    # 复用上一轮结果：挑选层与判定层都不再跑。恒等式左端
                    # （候选帧 ⊇ 判定通过）由上一轮保证，这里不要重新求交——
                    # 上一轮的候选帧可能就是这一轮抽到的那批，重复收窄只会误伤。
                    logger.info(
                        "复用上一轮画面判定结果：判定通过=%d 张，跳过挑选与判定",
                        len(self.approved_shots),
                    )
                else:
                    picked = self._pick_note_frames(gpt, transcript, task_id=task_id)
                    # 判定集合 = 挑选结果 ∩ 实际抽到的候选帧。
                    # 第一次调用只看字幕，它挑的时间点未必都真抽到了帧（去重、抽帧
                    # 失败、配额截断都会让实际帧少于一厢情愿的清单），所以必须求
                    # 交集，否则恒等式「候选帧 ⊇ 判定通过」会被打破。
                    candidate_set = {
                        round(_safe_float(t), 3) for t in (self.frame_candidates or [])
                    }
                    if candidate_set:
                        # 吸附而不是精确相等：挑选层的时间戳来自字幕（小数），候选帧
                        # 来自抽帧（整秒），两者本来就对不齐。精确相等会把模型挑中的
                        # 点几乎全部丢弃，等于白跑两次 LLM 调用。
                        matched = _match_candidate_frames(picked, candidate_set)
                        if len(matched) != len(picked):
                            logger.info(
                                "挑选层吸附到候选帧 %d/%d（其余 %d 个时间点附近没有帧，已忽略）",
                                len(matched),
                                len(picked),
                                len(picked) - len(matched),
                            )
                        picked = matched
                    else:
                        logger.warning(
                            "本次没有抽到任何候选帧，挑选结果 %d 个时间点全部无法定位到画面",
                            len(picked),
                        )
                        picked = []
                    self.frame_candidates = list(self.frame_candidates or [])
                    # 挑选结果必须留在实例上：重试时既要复用它，也要靠它和候选帧
                    # 一起判断「这次是不是真的算过了」。只放在局部变量里的话，
                    # 重试回来就没有任何证据说明挑选层跑过了。
                    self.picked_frames = list(picked)
                    self.approved_shots = self._judge_note_frames(
                        gpt, transcript, task_id=task_id, candidates=picked
                    )
                    # 两次调用都成功之后才落盘。中途失败时写盘会把「判定通过 = 空」
                    # 这种未完成状态固化下来，反而让下一次重试以为已经算完了。
                    self._save_ocr_cache(str(video_url))

            # 2.6 OCR 层：对判定通过的每一张图跑 OCR，结果作为参考喂给总结模型。
            #
            # 位置很关键（m04502 用户澄清 + q6_ocr_stage）：必须在**出笔记的那次
            # 总结之前**跑完，因为 OCR 文本要进总结提示词。原先它在
            # _post_process_markdown 里（总结之后），那时 OCR 结果只能用来决定
            # 「插图还是回填文字」，没法给模型当参考。
            # self.video_path 在类型上是 Optional，但走到这里必然已经下载过视频；
            # 显式收窄，缺了它宁可跳过 OCR 层也不要把 None 漏进 generate_screenshot。
            if self.ocr_judgement_enabled and self.approved_shots and self.video_path:
                if self.ocr_texts is None:
                    self._run_ocr_stage(
                        video_path=self.video_path, task_id=task_id
                    )
                else:
                    logger.info(
                        "复用上一轮 OCR 结果：图片=%d 张，跳过 OCR task_id=%s",
                        len(self.ocr_texts),
                        task_id,
                    )

            # 参考块：把判定通过的每张图的 OCR 结果按时间点渲染成文本，进总结提示词。
            # 渲染放在这里而不是 OCR 阶段里，是因为 approved_shots 可能是从磁盘缓存
            # 复用的，那时 ocr_texts 也要一并复用——两处都渲染会分叉。
            ocr_reference = ""
            if self.ocr_judgement_enabled and self.approved_shots:
                from app.services.ocr_assist import build_ocr_reference

                ocr_reference = build_ocr_reference(
                    self.approved_shots, self.ocr_texts or {}
                )

            # 图片输入换成判定通过的**单帧**（q10/q11）。
            #
            # 原来喂的是 self.video_img_urls —— 那是 VideoReader 把每 9 帧拼成一张的
            # **网格图**（127 张）。网格图是判定层的工作材料，不是给笔记模型看的：
            # 每帧被缩到 1/9，模型看不清板书细节；而且它包含大量未通过判定的帧。
            # 判定通过的这张清单本来就是「必须编入笔记」的集合，直接送它最合适。
            shot_urls = [u for u in (self.shot_image_urls or []) if u]
            prompt_img_urls = shot_urls or list(self.video_img_urls or [])

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
                video_img_urls=prompt_img_urls,
                ocr_reference=ocr_reference,
                ocr_assist=self.ocr_assist,
                approved_shots=self.approved_shots,
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
            self._save_metadata(
                video_id=audio_meta.video_id,
                platform=platform,
                task_id=task_id,
                group_id=self.group_id,
            )

            # 6. 完成
            self._update_status(task_id, TaskStatus.SUCCESS)
            logger.info(f"笔记生成成功 (task_id={task_id})")
            return NoteResult(
                markdown=markdown, transcript=transcript, audio_meta=audio_meta
            )

        except Exception as exc:
            logger.error(f"生成笔记流程异常 (task_id={task_id})：{exc}", exc_info=True)
            self._update_status(task_id, TaskStatus.FAILED, message=str(exc))
            # 429 优先于 non_retryable：转写层历史上把 429 也标成了不可重试
            # （那时「不可重试」是唯一能表达「别重跑整条流水线」的手段），
            # spec 012 起 429 改走等待路径，所以这里必须先判它。
            self.last_error_rate_limited = is_rate_limit_error(exc)
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

    def _ocr_cache_file(self, video_url: str) -> Path:
        """本次任务的 OCR 辅助中间结果落盘位置。

        用 video_url 的短哈希做文件名（不是 task_id）：重试会换一个新的 task_id，
        但复用要跨 task_id 生效，所以键必须是「哪个视频」而不是「哪一次尝试」。

        用 sha256 而不是 sha1：这不是安全场景（没有对抗方），但弱哈希在这类
        「拿 URL 生成标识」的用途上会触发静态规则告警，而换算法的代价是零。
        """
        key = hashlib.sha256(str(video_url).encode("utf-8")).hexdigest()[:16]
        return NOTE_OUTPUT_DIR / f"ocr_frames_{key}.json"

    def _load_ocr_cache(self, video_url: str, need_ocr: bool = False) -> bool:
        """从磁盘读取上一轮的抽帧/挑选/判定结果；读到就填进实例并返回 True。

        只在内存里没有结果时才起作用的兜底：正常重试走的是「同一实例 + 不重置」，
        但进程重启（或换 worker）之后实例状态就没了，而抽帧几十分钟、两次 LLM 调用
        也不便宜，所以这里再给一层持久化。读失败一律当缓存不存在，不影响任务。

        ``need_ocr=True`` 时要求缓存必须带 OCR 结果：缓存里记着写它时 OCR 开没开，
        上一次是关的、这一次要开，就不能复用——否则图上文字永远补不回来。
        """
        if self.approved_shots is not None:
            return False
        path = self._ocr_cache_file(video_url)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            approved = data.get("approved_shots")
            if approved is None:
                return False
            cached_ocr = bool(data.get("ocr_enabled"))
            if need_ocr and not cached_ocr:
                logger.info("磁盘缓存来自未启用 OCR 的一轮，本次需要 OCR，改为重新判定")
                return False
            self.ocr_cache_used_ocr = cached_ocr
            self.frame_candidates = [
                _safe_float(t) for t in (data.get("frame_candidates") or [])
            ]
            self.picked_frames = [
                _safe_float(t) for t in (data.get("picked_frames") or [])
            ]
            # 判定结果是 dataclass 清单，落盘时用 asdict；读回来必须还原成
            # WorthDecision，否则下游 getattr(decision, "time") 会全部取不到值。
            from app.services.ocr_assist import WorthDecision

            self.approved_shots = [
                WorthDecision(**item) if isinstance(item, dict) else item
                for item in approved
            ]
            # q5_cache=A：OCR 文本一起复用。老缓存没有这个字段 → ocr_texts 保持
            # None，调用方据此重跑 OCR 层（而不是当成「OCR 返回空」把参考块丢掉）。
            ocr_payload = data.get("ocr_texts")
            if isinstance(ocr_payload, dict) and ocr_payload:
                restored: dict = {}
                for key, value in ocr_payload.items():
                    reading = _deserialize_ocr_result(value)
                    if reading is None:
                        # 单条坏了就丢这一条，别让整份缓存作废。
                        continue
                    try:
                        restored[float(key)] = reading
                    except (TypeError, ValueError):
                        continue
                self.ocr_texts = restored or None
                self.ocr_failures = int(data.get("ocr_failures") or 0)

            logger.info(
                "已从磁盘复用 OCR 辅助结果：候选帧=%d 挑选=%d 判定通过=%d OCR=%d",
                len(self.frame_candidates),
                len(self.picked_frames),
                len(self.approved_shots),
                len(self.ocr_texts or {}),
            )
            return True
        except Exception as exc:
            logger.warning(f"读取 OCR 辅助缓存失败，将重新计算：{exc}")
            return False

    def _save_ocr_cache(self, video_url: str) -> None:
        """把抽帧/挑选/判定结果落盘，供重试或进程重启后复用。"""
        path = self._ocr_cache_file(video_url)
        try:
            payload = {
                "video_url": str(video_url),
                "frame_candidates": list(self.frame_candidates or []),
                "picked_frames": list(self.picked_frames or []),
                "approved_shots": [
                    asdict(s) if is_dataclass(s) else s
                    for s in (self.approved_shots or [])
                ],
                # q5_cache=A：OCR 文本一并落盘，重试时不必再调一次 OCR。
                # 键是时间点，转成字符串再写（JSON 的键只能是字符串）。
                # OcrResult 是 OcrBlock 列表 + raw 字典，json 处理不了 dataclass，
                # 先展开成纯 dict 再写。raw 里带着 md_results 原文（q1 要它）。
                "ocr_texts": {
                    str(key): _serialize_ocr_result(value)
                    for key, value in (self.ocr_texts or {}).items()
                },
                "ocr_failures": int(self.ocr_failures or 0),
                # 这个标记决定这份缓存能不能被「本次要跑 OCR」的调用复用。
                "ocr_enabled": bool(self.ocr_assist),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            temp_file = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
            with temp_file.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            temp_file.replace(path)
            logger.info("OCR 辅助结果已落盘，重试可直接复用：%s", path.name)
        except Exception as exc:
            # 落盘只是优化，失败不能影响任务本身。
            logger.warning(f"写入 OCR 辅助缓存失败（不影响本次任务）：{exc}")

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

    # ---------------- OCR 辅助模式（spec 008 ticket 02） ----------------

    def _resolve_ocr_assist(self, override: Optional[bool] = None) -> bool:
        """OCR 辅助是否已启用且可用。

        - 未启用 → False，整条流程与改动前完全一致（spec 008 §5.5）；
        - 已启用但配置不全 → 抛错让任务失败并指向设置页，**不静默降级**：
          用户明确打开了这个开关，悄悄退回老路径会让人以为它生效了。

        ``override`` 是「这一次任务」的开关（spec 008 ticket 02）：设置页管
        「配没配好」，生成表单管「这次用不用」。``None`` 表示沿用全局设置。
        显式 ``False`` 会直接短路——用户这次不想用，就不该因为全局没配好而失败。
        """
        # 这里比对的是**三态**：None（沿用全局）、True（本次强制开）、
        # False（本次强制关），所以必须用 `is False` 精确匹配——写成
        # `== False` 会把 0、"" 这类假值也算作「明确关闭」，
        # 把「没指定」误当成「用户关了」。
        if override is False:
            return False
        from app.services.ocr_config_manager import ENDPOINT_PATH, OcrConfigManager

        readiness = OcrConfigManager().is_ready()
        if override is None and not readiness.get("enabled"):
            return False
        if override is True and not readiness.get("enabled"):
            # 按任务开了但全局配置页还没打开开关：配置本身可能是齐的，
            # 所以继续往下走 readiness 检查，而不是直接判死。
            logger.info("本次任务指定使用 OCR 辅助（全局开关未启用，按任务覆盖）")
        if not readiness.get("ready"):
            raise Exception(
                readiness.get("reason")
                or "OCR 辅助未配置完成，请前往「设置 → OCR 辅助」"
            )
        # 协议已收敛成常量（spec 008 ticket 01 §6），readiness 里不再有 protocol 键；
        # 留在这里会打出 protocol=None，反而让人以为协议没定下来。
        logger.info(
            "OCR 辅助就绪：endpoint=%s model=%s",
            ENDPOINT_PATH,
            readiness.get("model_name"),
        )
        return True

    def _pick_note_frames(self, gpt, transcript, task_id: Optional[str] = None) -> list:
        """第一次调用：从字幕里挑出「值得看一眼画面」的时间点（spec 008 ticket 02）。

        这是 m02642 `q1_call_shape=B` 定下的**两次调用**里的第一次。它与
        `_judge_note_frames` 的分工是刻意分开的：

        * 本方法只看字幕，负责把「可能值得截图」的位置缩小到一个可判定的集合；
        * `_judge_note_frames` 再看网格图，决定这个集合里哪些**真的**进笔记。

        为什么不能合成一次调用：一次回答里既出挑选结果又出判定结果，两者会互相
        污染（模型会为了「凑够判定条数」而虚报值得挑的帧）。分成两次后，第二次的
        输入是第一次的输出，责任边界清晰、也各自可单独重跑。

        m02661 `q1_pick_input=A`：候选可能一两百帧、网格图三十多张，一次全塞进去
        是 814 秒耗时的主要来源，因此这里沿用 `RequestChunker` 的分块思路——
        `plan_frame_timestamps` 内部按 `MAX_PLAN_SEGMENTS` 抽稀字幕，调用方再把
        多块结果合并去重。

        与 `_plan_frames_with_llm` 的区别：那个服务于 hybrid 采样的配额
        （`HYBRID_LLM_RATIO`），失败可以静默退回均匀采样；本方法是 OCR 辅助模式下
        插图的唯一入口，**失败必须让任务失败**（m02642 `q6_judge_fail=A`）。
        """
        if not hasattr(gpt, "plan_frame_timestamps"):
            raise Exception(
                "当前模型不支持画面挑选，无法使用 OCR 辅助模式（请换一个支持对话的模型）"
            )

        self._update_status(
            task_id,
            TaskStatus.SUMMARIZING,
            stage=TaskStage.SUMMARIZING,
            message="正在挑选值得编入笔记的画面",
            detail={"stage": "pick_frames"},
        )

        duration = self._probe_duration()
        started = time.perf_counter()
        try:
            from app.services.ocr_assist import MAX_JUDGE_CANDIDATES

            picks = gpt.plan_frame_timestamps(
                transcript.segments if transcript else [],
                duration=duration,
                max_items=MAX_JUDGE_CANDIDATES,
            )
        except Exception as exc:
            logger.error("画面挑选失败：%s", exc)
            self._handle_exception(task_id, exc)
            raise

        # 合并去重并保持时间升序：分块调用会返回多批结果，重叠部分是正常的。
        picked = sorted(
            {round(_safe_float(t), 3) for t in (picks or []) if _safe_float(t) >= 0}
        )
        elapsed = time.perf_counter() - started
        # 六层日志之「挑选层」
        logger.info(
            "OCR 辅助挑选层：字幕分段=%d 挑中=%d 耗时=%.3fs task_id=%s",
            len(transcript.segments) if transcript else 0,
            len(picked),
            elapsed,
            task_id,
        )
        if not picked:
            raise Exception(
                "没能从字幕里挑出任何值得截图的画面，OCR 辅助模式无法继续（"
                "请确认视频有可用字幕，或关闭「设置 → OCR 辅助」后重试）"
            )
        return picked

    def _probe_duration(self) -> float:
        """探测视频时长；失败返回 0（调用方按「未知」处理，不阻断流程）。"""
        if not self.video_path:
            return 0.0
        try:
            from app.utils.audio_helper import probe_duration_seconds

            return _safe_float(probe_duration_seconds(str(self.video_path)))
        except Exception:
            logger.warning("探测视频时长失败，提示词里的时长按未知处理")
            return 0.0

    def _judge_note_frames(
        self,
        gpt,
        transcript,
        task_id: Optional[str] = None,
        candidates: Optional[list] = None,
    ) -> list:
        """第二次调用：让 LLM 看网格图，判定哪些候选帧值得编入笔记。

        返回值就是「允许编入笔记」的全部来源。异常一律向上抛（网络失败、解析失败
        都算），因为静默返回空清单会让整篇笔记在用户毫无察觉的情况下没有插图
        （spec 008 §5.6b）。

        ``candidates`` 缺省时退回 ``self.frame_candidates``（抽帧实际产出的时间点），
        但 OCR 辅助模式下应当由 `_pick_note_frames` 的挑选结果显式传入——判定集合
        先被第一次调用缩小过，才能把网格图和判定调用压在一个可接受的成本内。
        """
        candidates = list(
            candidates if candidates is not None else (self.frame_candidates or [])
        )
        if not candidates:
            # 没有候选帧不算失败：用户可能没开视频理解，或者抽帧确实一张都没成功。
            logger.warning("OCR 辅助已启用，但本次没有候选帧，笔记不会插入任何图片")
            return []

        if not hasattr(gpt, "judge_note_frames"):
            raise Exception("当前模型客户端不支持画面价值判定，无法使用 OCR 辅助模式")

        self._update_status(
            task_id,
            TaskStatus.SUMMARIZING,
            stage=TaskStage.SUMMARIZING,
            message=f"正在判定哪些画面值得编入笔记（{len(candidates)} 个候选）",
            detail={"candidates": len(candidates)},
        )

        duration = 0.0
        if self.video_path:
            try:
                from app.utils.audio_helper import probe_duration_seconds

                duration = _safe_float(probe_duration_seconds(str(self.video_path)))
            except Exception:
                logger.warning("探测视频时长失败，判定提示词里的时长按未知处理")

        try:
            outcome = gpt.judge_note_frames(
                transcript.segments if transcript else [],
                candidates,
                duration=duration,
                image_urls=self.video_img_urls,
            )
        except Exception as exc:
            logger.error(f"画面价值判定失败：{exc}")
            self._handle_exception(task_id, exc)
            raise

        logger.info("画面价值判定：%s", outcome.describe())
        approved = list(outcome.approved)
        if not approved:
            logger.warning("画面价值判定：没有任何候选帧被判为值得编入笔记")
        return approved

    def _cleanup_previous_screenshots(self, approved: List[Any]) -> None:
        """删掉本轮要重新生成的截图文件，避免重试时留下没人引用的残骸。

        只按**本轮判定通过的时间点**删除，不扫目录、不按任务前缀批量清空：
        同一秒的截图文件名是固定的（`shot_<秒>.jpg`），所以重试要么覆盖它，
        要么留下一个永远没人引用的旧文件。只删这两种情况里的后一种。

        失败只记日志：清不掉最坏也只是多占几 MB，不该让任务失败。
        """
        directory = Path(IMAGE_OUTPUT_DIR)
        if not directory.is_dir():
            return
        removed = 0
        for decision in approved or []:
            ts = _safe_int(round(_safe_float(getattr(decision, "time", 0) or 0), 0))
            target = directory / f"shot_{ts}.jpg"
            try:
                if target.is_file():
                    target.unlink()
                    removed += 1
            except OSError as exc:
                logger.warning("清理上一轮截图失败（忽略）：%s：%s", target.name, exc)
        if removed:
            logger.info(
                "重试前清理上一轮截图 %d 张 task_id 无关（按时间点覆盖）", removed
            )

    def _run_ocr_stage(
        self, video_path: Union[str, Path], task_id: Optional[str] = None
    ) -> None:
        """OCR 阶段：为判定通过的每张图生成单独截图并识别（m04445 pivot）。

        为什么从 _post_process_markdown 搬到这里（q6_ocr_stage + m04502 澄清）：
        「出笔记的那次总结」需要一个参考块，里面是图上抄回来的全部内容。OCR 若仍
        留在总结之后，它产出的文本就永远赶不上那趟车，只能反过来决定「这张图插图
        还是用文字顶替」——那正是用户反馈的「没有插入图片」。

        这一步做三件事，顺序不能换：
          1. 生成单帧截图（不是网格图）。网格图是把若干帧拼成的一张图，模型看到
             的是缩小的拼贴；q11 明确要求送判定通过的那几张单独截图。
          2. 逐张 OCR。单张失败只跳过该张（q4_ocr_failure=A），图照插、任务照跑，
             但计入 self.ocr_failures 并进日志——参考内容静默缺失最难排查。
          3. 把结果按时间点存进 self.ocr_texts，把图片 URL 存进 self.shot_image_urls。

        恒等式（q8_invariant=A）：判定通过 ＝ 实际插图。OCR 成功与否都不再改变插图
        集合，这里只决定「能不能额外给模型一份文字参考」。
        """
        from app.services.ocr_assist import classify_ocr_result, format_mmss
        from app.utils.video_helper import generate_screenshot

        approved: list = list(self.approved_shots or [])
        if not approved:
            self.ocr_texts = {}
            self.shot_image_urls = []
            return

        video_path = str(video_path)

        total = len(approved)
        self._update_status(
            task_id,
            TaskStatus.FORMATTING,
            stage=TaskStage.POST_PROCESSING,
            message=f"正在识别 {total} 张画面的文字",
            stage_progress=0,
            detail={"current": 0, "total": total, "unit": "screenshots"},
        )

        ocr_client: Optional[Any] = None
        if self.ocr_assist:
            try:
                from app.services.ocr_client import build_ocr_client

                ocr_client = build_ocr_client()
            except Exception as exc:
                # 设置里说「就绪」但客户端建不起来，属于配置漂移；跳过 OCR 而不是
                # 让整篇笔记失败，与 q4 的容错口径一致。
                logger.warning(f"OCR 客户端不可用，本次跳过 OCR 层：{exc}")

        started = time.perf_counter()
        ocr_texts: dict = {}
        shot_urls: list = []
        failures = 0

        for index, decision in enumerate(approved, 1):
            raw_seconds = getattr(decision, "time", None)
            seconds = float(raw_seconds or 0)
            label = format_mmss(seconds) if raw_seconds is not None else "?"

            img_path = None
            try:
                # 与 _insert_approved_screenshots 用同一套落盘口径：
                # generate_screenshot(video_path, output_dir, timestamp, index)
                # 文件名是 shot_<index>.jpg，后处理阶段按同一编号回填占位符。
                ts = int(round(seconds))
                img_path = generate_screenshot(
                    video_path, str(IMAGE_OUTPUT_DIR), ts, index
                )
            except Exception as exc:
                logger.warning(
                    "OCR 辅助截图失败（该图仍会插入笔记，但可能缺图）：%s @ %s：%s",
                    label,
                    seconds,
                    exc,
                )

            if img_path:
                try:
                    from app.services.media_resource_service import register_resource

                    register_resource("screenshot", str(img_path), task_id=task_id)
                except Exception:
                    logger.exception("无法登记生成的截图 task_id=%s", task_id)
                shot_urls.append(self._image_to_data_url(str(img_path)))

            reading = None
            ocr_result = None
            if img_path and ocr_client is not None:
                try:
                    ocr_result = ocr_client.recognize_image(img_path)
                    reading = classify_ocr_result(ocr_result)
                except Exception as exc:
                    failures += 1
                    logger.warning(
                        "OCR 辅助识别失败，跳过该张的参考内容（图照插）：%s @ %s：%s",
                        label,
                        seconds,
                        exc,
                    )

            if ocr_result is not None:
                # 存 **OcrResult** 而不是 OcrReading：q1_ocr_payload=A 要的是
                # 「所有 label 的 content + bbox + md_results 原文」，而 OcrReading
                # 是分流用的瘦身视图（只有 parts/part_labels/content_chars），
                # 不含 bbox 与 md_results。reading 仍用于分类判定与日志。
                ocr_texts[seconds] = ocr_result
                logger.info(
                    "OCR 辅助识别 %d/%d：%s label=%s 正文=%d 字 task_id=%s",
                    index,
                    total,
                    label,
                    reading.label_text if reading is not None else "(无元素)",
                    reading.content_chars if reading is not None else 0,
                    task_id,
                )
            else:
                logger.info(
                    "OCR 辅助识别 %d/%d：%s 无可用文字（图仍会插入）task_id=%s",
                    index,
                    total,
                    label,
                    task_id,
                )

        self.ocr_texts = ocr_texts
        self.ocr_failures = failures
        self.shot_image_urls = shot_urls

        # 六层日志之「OCR 层」（m02661 q5_log_layers=A）。
        logger.info(
            "OCR 辅助 OCR 层：判定通过=%d 截图=%d OCR成功=%d OCR失败=%d 耗时=%.3fs task_id=%s",
            total,
            len(shot_urls),
            len(ocr_texts),
            failures,
            time.perf_counter() - started,
            task_id,
        )

    def _image_to_data_url(self, path: str) -> str:
        """把本地图片读成 data URL，供多模态消息使用；失败返回空串。"""
        try:
            with open(path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("ascii")
        except Exception as exc:
            logger.warning(f"读取截图失败，该图不会作为图像送入模型：{path}：{exc}")
            return ""
        suffix = Path(path).suffix.lower().lstrip(".") or "jpeg"
        mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
        return f"data:image/{mime};base64,{encoded}"

    def _insert_approved_screenshots(
        self,
        markdown: str,
        video_path: Path,
        approved: List[Any],
        task_id: Optional[str] = None,
        ocr_enabled: bool = True,
    ) -> str:
        """把判定通过的截图回填进 `[[SHOT-n]]` 占位符；OCR 已在更早的一层跑完。

        与 `_insert_screenshots` 的分工：那个服务于「模型自己说要在哪插图」的老
        路径，本方法服务于「只有判定通过的才插图」的新路径。两者互不调用，老路径
        零回归风险。

        恒等式（spec 008 ticket 02，m04445 pivot 后）：
            候选帧 ⊇ 判定通过 ＝ 实际插图
        OCR 成败**不**在这条等式里——它只决定「有没有额外文字参考可送给模型」。

        本方法**一律插图**，不因 OCR 读出了什么而改用文字顶替：一张板书越清晰、
        文字越抄得下来，越容易触发「以文字顶替」，于是笔记里恰恰看不到那张最该被
        看到的图。OCR 文本的去处是总结提示词里的参考块（`build_ocr_reference`），
        不是正文，所以这里既不构造引用块，也不跑 OCR。

        ``ocr_enabled`` 是旧调用点的兼容参数，本方法已不再读它（OCR 层移到
        `_run_ocr_stage`）；保留只为不改调用方的签名。
        """
        from app.services.ocr_assist import format_mmss

        approved = list(approved or [])
        # 重试会重新走到这里，而上一轮已经往 static/screenshots 落过图、markdown 缓存
        # 里也已经写着那些 URL 了。同一时间点重复生成只会留下没人引用的残骸，
        # 所以按时间点清一次（只清本轮要生成的，不碰其他任务的截图）。
        self._cleanup_previous_screenshots(approved)

        # 模型可能顺手写了遗留的 *Screenshot-... 标记。它们没有经过价值判定，
        # 一律剥掉——这正是「只有 LLM 评为需要编入笔记的才编入」的结构性保证。
        legacy = extract_screenshot_timestamps(markdown)
        if legacy:
            logger.warning(
                "OCR 辅助模式下发现 %d 个未经判定的截图标记，已移除", len(legacy)
            )
            for marker, _ts in legacy:
                markdown = markdown.replace(marker, "", 1)

        if not approved:
            return markdown

        total = len(approved)
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

        # 注意：本方法**不再**构造 OCR client。识别已搬到 _run_ocr_stage（q6），
        # 那边建一个 client、串行跑完全部判定通过的图；这里重复建只会浪费一次
        # 配置读取。`ocr_enabled` 参数保留仅为兼容旧调用点的签名。
        def _render(item):
            """抽图 + OCR。两件事都是等待型 I/O，放在同一个 worker 里最省事。"""
            nonlocal completed
            idx, decision = item
            ts = _safe_int(round(_safe_float(getattr(decision, "time", 0) or 0), 0))
            img_path = generate_screenshot(
                str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx + 1
            )
            if not img_path:
                raise RuntimeError(f"生成截图失败：第 {idx + 1} 张（{ts}s）")
            try:
                from app.services.media_resource_service import register_resource

                register_resource(
                    "screenshot", img_path, task_id=task_id, source="generated"
                )
            except Exception:
                logger.exception("无法登记生成的截图 task_id=%s", task_id)

            # OCR 已经不在这一步做了（m04445 pivot + q6_ocr_stage）：识别搬到
            # _run_ocr_stage，跑在总结之前，结果进提示词当参考。这里只负责把
            # 判定通过的图抽出来并回填占位符——OCR 成败不再影响插图集合。
            filename = Path(img_path).name
            img_url = f"{IMAGE_BASE_URL.rstrip('/')}/{filename}"
            with counter_lock:
                completed += 1
                current = completed
            self._update_status(
                task_id,
                TaskStatus.FORMATTING,
                stage=TaskStage.POST_PROCESSING,
                message=f"正在处理截图 {current}/{total}",
                stage_progress=current / total * 100,
                detail={"current": current, "total": total, "unit": "screenshots"},
            )
            logger.info(
                "OCR 辅助插图单张：第 %d/%d 张 时间=%ss 文件=%s task_id=%s",
                idx + 1,
                total,
                ts,
                filename,
                task_id,
            )
            return idx, decision, img_url

        workers = max(1, min(8, os.cpu_count() or 4, total))
        ocr_started = time.perf_counter()
        if workers == 1:
            rendered = [_render(item) for item in enumerate(approved)]
        else:
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="ocr_shot"
            ) as executor:
                rendered = list(executor.map(_render, list(enumerate(approved))))
        logger.info(
            "OCR 辅助 OCR 层：共 %d 张 成功=%d 耗时=%.3fs task_id=%s",
            total,
            len(rendered),
            time.perf_counter() - ocr_started,
            task_id,
        )

        inserted = 0
        missing = []
        embedded = 0
        for idx, decision, img_url in sorted(rendered, key=lambda row: row[0]):
            caption = (getattr(decision, "caption", "") or "").strip()
            alt = f"截图 {format_mmss(getattr(decision, 'time', 0) or 0)}"

            # m04445 pivot（q3_quote_block=A + q8_invariant=A）：判定通过的图**一律
            # 插图**，不再因为「OCR 读出了文字」就用引用块把它顶掉。
            #
            # 用户的原话是「无论 ocr 有没有返回内容，大模型评估应该插入的图片都应该
            # 被插入」。原先的分流有个隐蔽后果：一张图画质清晰、文字能抄下来，反而
            # 最容易触发「以文字顶替」——于是笔记里看不到那张图，用户直接反馈
            # 「可是没有插入图片」。OCR 文本现在的用途是**给模型当参考**
            # （进总结提示词），而不是替掉图片本身。
            block = f"![{caption or alt}]({img_url})"

            new_markdown, count = _shot_marker_pattern(idx + 1).subn(
                lambda _match, _block=block: _block, markdown, count=1
            )
            if count:
                markdown = new_markdown
                inserted += 1
            else:
                missing.append((idx, decision, block))

        # 实际插图 = 回填成功 + 漏插后追加。必须在 missing 收集完之后才算。
        embedded = inserted + len(missing)

        if missing:
            # 模型漏插占位符时不能丢内容（用户要的正是「保留化学公式和立体几何」），
            # 统一追加到笔记末尾的「补充截图」小节。
            logger.warning(
                "有 %d 个判定通过的截图点模型没有插入占位符，已追加到笔记末尾",
                len(missing),
            )
            appendix = ["", "---", "", "## 补充截图", ""]
            for idx, decision, block in missing:
                reason = (getattr(decision, "reason", "") or "").strip()
                heading = format_mmss(getattr(decision, "time", 0) or 0)
                appendix.append(f"### {heading}" + (f" · {reason}" if reason else ""))
                appendix.append("")
                appendix.append(block)
                appendix.append("")
            markdown = markdown.rstrip() + chr(10) + chr(10).join(appendix)

        logger.info(
            "OCR 辅助插图：候选帧=%d 判定通过=%d 截图=%d 实际插图=%d "
            "占位符命中=%d 追加=%d OCR成功=%d OCR失败=%d",
            len(self.frame_candidates or []),
            len(approved),
            len(rendered),
            embedded,
            inserted,
            len(missing),
            len(self.ocr_texts or {}),
            int(self.ocr_failures or 0),
        )
        # 恒等式（q8_invariant=A）：判定通过 ＝ 实际插入。
        #
        # 实际插图 = 回填成功的 inserted ＋ 模型漏插占位符后追加到末尾的 missing。
        # 两者都在 markdown 里落了 `![](...)`，所以这个等式是真的守恒量；
        # 原先这里比的是 len(rendered)，那只说明「截图都生成了」，不说明「都插进去了」。
        # OCR 成功与否不再影响插图集合，所以它只报计数、不参与校验。
        if embedded != len(approved):
            logger.warning(
                "OCR 辅助插图计数不一致：判定通过=%d 实际插图=%d（占位符命中=%d 追加=%d）",
                len(approved),
                embedded,
                inserted,
                len(missing),
            )
        return markdown

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

        from app.services.transcriber_config_manager import TranscriberConfigManager
        cm = TranscriberConfigManager()
        return get_transcriber(
            transcriber_type=self.transcriber_type,
            model_size=self.model_size,
            transcriber_options=transcriber_options,
            device=cm.get_whisper_device(),
            compute_type=cm.get_whisper_compute_type(),
            cpu_threads=cm.get_whisper_cpu_threads(),
            num_workers=cm.get_whisper_num_workers(),
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
            raise ProviderError(
                code=ProviderErrorEnum.NOT_FOUND,
                message=ProviderErrorEnum.NOT_FOUND.message,
            )
        logger.info(f"创建 GPT 实例 {provider_id}")
        config = ModelConfig(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
            model_name=model_name,
            provider=provider["type"],
            name=provider["name"],
            # spec 007：供应商级限流。provider dict 里缺这两个键（老库）时给
            # None，UniversalGPT 会退化到默认值（4 并发 / 600 RPM）。
            provider_key=str(provider.get("id") or provider_id or ""),
            max_concurrency=provider.get("max_concurrency"),
            max_rpm=provider.get("max_rpm"),
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
            raise NoteError(
                code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message,
            )
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
            normalized_progress = global_progress(
                resolved_stage, normalized_stage_progress
            )

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
            temp_file = status_file.with_name(
                f"{status_file.name}.{uuid.uuid4().hex[:8]}.tmp"
            )
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
        error_message = getattr(exc, "detail", str(exc))
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
                detail={
                    "current": current,
                    "total": total,
                    "unit": "frames" if "frame" in stage else "grids",
                },
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
        self._update_status(
            task_id,
            status_phase,
            stage=TaskStage.DOWNLOADING_AUDIO,
            message="准备下载音频",
        )

        # 已有缓存，尝试加载
        if audio_cache_file.exists():
            logger.info(f"检测到音频缓存 ({audio_cache_file})，直接读取")
            try:
                data = json.loads(audio_cache_file.read_text(encoding="utf-8"))
                cached = AudioDownloadResult(**data)
                # 缓存里存的是绝对路径，但那个文件会被媒体清理（容量维度/过期维度）
                # 删掉。只认缓存不认文件，任务就会拿着一个已经不存在的路径去转写，
                # 报出来的是「No such file or directory」甚至误导性的 asdict 错误。
                if cached.file_path and Path(cached.file_path).is_file():
                    return cached
                logger.warning(
                    "音频缓存已失效（文件不存在：%s），将重新下载", cached.file_path
                )
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
                    # 六层日志之「抽帧层」（interval 分支）：与 smart/hybrid 分支同一
                    # 口径，两类采样各有各的耗时来源，日志必须能分别归因。
                    frame_started = time.perf_counter()
                    self._update_status(
                        task_id,
                        TaskStatus.DOWNLOADING,
                        message="正在抽取视频画面并拼接网格图",
                        stage=TaskStage.EXTRACTING_FRAMES,
                    )
                    reader = VideoReader(
                        video_path=str(self.video_path),
                        grid_size=tuple(grid_size),
                        frame_interval=frame_interval,
                        unit_width=960,
                        unit_height=540,
                        save_quality=80,
                        progress_callback=self._video_progress_callback(task_id),
                        task_id=task_id,
                    )
                    self.video_img_urls = reader.run()
                    # 候选帧 = 真正抽出来并进了网格图的时间点（spec 008 ticket 02）
                    self.frame_candidates = list(reader.candidate_timestamps)
                    logger.info(
                        "OCR 辅助抽帧层：采样=%s 候选帧=%d 网格图=%d 耗时=%.3fs task_id=%s",
                        sampling_mode or "interval",
                        len(self.frame_candidates),
                        len(self.video_img_urls or []),
                        time.perf_counter() - frame_started,
                        task_id,
                    )
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
            audio_cache_file.write_text(
                json.dumps(asdict(audio), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                from app.services.media_resource_service import register_resource

                if Path(audio.file_path).is_file():
                    register_resource(
                        "audio",
                        audio.file_path,
                        task_id=task_id,
                        video_id=audio.video_id,
                    )
                if audio.video_path and Path(audio.video_path).is_file():
                    register_resource(
                        "video",
                        audio.video_path,
                        task_id=task_id,
                        video_id=audio.video_id,
                    )
                if self.video_path and self.video_path.is_file():
                    register_resource(
                        "video",
                        self.video_path,
                        task_id=task_id,
                        video_id=audio.video_id,
                    )
            except Exception:
                logger.exception("无法登记任务媒体资源 task_id=%s", task_id)
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
                segments = [
                    TranscriptSegment(**seg) for seg in data.get("segments", [])
                ]
                return TranscriptResult(
                    language=data.get("language"),
                    full_text=data["full_text"],
                    segments=segments,
                )
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
                        encoding="utf-8",
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
                segments = [
                    TranscriptSegment(**seg) for seg in data.get("segments", [])
                ]
                return TranscriptResult(
                    language=data["language"],
                    full_text=data["full_text"],
                    segments=segments,
                )
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

            if transcript is None:
                # 走到这里说明转写器自己吞掉了异常（历史行为）。直接点名真实原因，
                # 不要让 asdict(None) 抛一个把排查引向错误方向的 TypeError。
                raise RuntimeError(
                    f"转写器没有返回结果（音频文件：{audio_file}），请确认该文件是否存在"
                )

            transcript_cache_file.write_text(
                json.dumps(asdict(transcript), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
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
        ocr_assist: bool = False,
        approved_shots: Optional[List] = None,
        ocr_reference: Optional[str] = None,
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
        :param ocr_assist: 是否走 OCR 辅助路径（决定截图指令的形态）
        :param approved_shots: 判定通过的截图清单，供提示词生成 [[SHOT-n]] 对照表
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
            # spec 008 ticket 02：OCR 辅助模式下截图指令换成编号占位符版本
            ocr_assist=ocr_assist,
            approved_shots=approved_shots,
            ocr_reference=ocr_reference,
        )

        try:
            summarize_started = time.perf_counter()
            markdown = gpt.summarize(source)
            elapsed = time.perf_counter() - summarize_started
            logger.info(
                "Visual pipeline phase=visual_model_requests seconds=%.3f image_count=%s configured_frames=%s",
                elapsed,
                len(video_img_urls or []),
                getattr(source, "extras", {}).get("max_frames")
                if isinstance(getattr(source, "extras", None), dict)
                else None,
            )
            # 六层日志之「总结层」（m02661 q5_log_layers=A）：输入字幕段数、喂进去的
            # 图片数、产出字符数、耗时。总结层此前完全没有日志，出了问题只能靠猜是
            # 模型慢还是输入太大。
            logger.info(
                "OCR 辅助总结层：字幕分段=%d 输入图片=%d 产出字符=%d 耗时=%.3fs task_id=%s",
                len(transcript.segments) if transcript else 0,
                len(video_img_urls or []),
                len(markdown or ""),
                elapsed,
                task_id,
            )
            write_started = time.perf_counter()
            markdown_cache_file.write_text(markdown, encoding="utf-8")
            logger.info(
                "Visual pipeline phase=note_write seconds=%.3f",
                time.perf_counter() - write_started,
            )
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
            if self.ocr_judgement_enabled:
                # 判定路径：只有判定通过的候选帧才会变成图片。这里故意不套
                # try/except —— OCR 失败必须让整个任务失败，绝不降级成
                # 「跳过 OCR 直接插图」（spec 008 ticket 02 §4）。
                markdown = self._insert_approved_screenshots(
                    markdown,
                    video_path,
                    self.approved_shots,
                    task_id=task_id,
                    # 开关只控制 OCR 层：判定照跑，插图集合不变，图上文字不回填。
                    ocr_enabled=self.ocr_assist,
                )
            else:
                try:
                    inserted = self._insert_screenshots(
                        markdown, video_path, task_id=task_id
                    )
                    if inserted is not None:
                        markdown = inserted
                except Exception:
                    logger.warning("截图插入失败，跳过该步骤")

        if "link" in formats:
            try:
                markdown = replace_content_markers(
                    markdown, video_id=audio_meta.video_id, platform=platform
                )
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
            img_path = generate_screenshot(
                str(video_path), str(IMAGE_OUTPUT_DIR), ts, idx
            )
            try:
                from app.services.media_resource_service import register_resource

                register_resource(
                    "screenshot", img_path, task_id=task_id, source="generated"
                )
            except Exception:
                logger.exception("无法登记生成的截图 task_id=%s", task_id)
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
                with ThreadPoolExecutor(
                    max_workers=workers, thread_name_prefix="screenshot"
                ) as executor:
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

    def _save_metadata(
        self, video_id: str, platform: str, task_id: str, group_id: str = None
    ) -> None:
        """
        将生成的笔记任务记录插入数据库（已存在则只更新归属）

        :param video_id: 视频 ID
        :param platform: 平台标识
        :param task_id: 任务 ID
        :param group_id: 所属分组；None 表示未分组
        """
        try:
            # 任务行通常在入队时就写好了（routers/note.py 的 _enqueue_task），
            # 这里再插一次会因为 task_id 唯一约束失败。所以先探一下：已经存在
            # 就只把分组归属补齐，不存在才插入。
            existing = get_video_task(task_id)
            if existing is not None:
                if group_id:
                    from app.db.note_group_dao import get_task_group

                    if get_task_group(task_id) != group_id:
                        assign_task_to_group(task_id, group_id)
                return
            insert_video_task(
                video_id=video_id, platform=platform, task_id=task_id, group_id=group_id
            )
            logger.info(
                f"已保存任务记录到数据库 (video_id={video_id}, platform={platform}, task_id={task_id})"
            )
        except Exception as e:
            logger.error(f"保存任务记录失败：{e}")
