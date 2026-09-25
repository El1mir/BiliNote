# app/routers/note.py
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator, model_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.note import NoteGenerator, logger
from app.services.task_serial_executor import task_serial_executor
from app.utils.response import ResponseWrapper as R
from app.downloaders.bilibili_expand import (
    build_video_id,
    build_video_url,
    fetch_collection,
    fetch_video_parts,
)
from app.utils.url_parser import (
    extract_video_id,
    normalize_video_url,
    parse_bilibili_collection_url,
)
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    video_id: str
    platform: str


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    # spec 002：interval=固定间隔抽帧；smart=画面变化+字幕分段高价值抽帧
    sampling_mode: Optional[str] = "interval"
    max_frames: Optional[int] = 60
    # 客户端（如浏览器插件）已经在用户浏览器里抓到字幕，直接传给后端复用，
    # 跳过 download_subtitles 和音频转写。形如：
    #   {"language": "zh", "full_text": "...", "segments": [{"start","end","text"}, ...]}
    prefetched_transcript: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_url(cls, data):
        # 稍后再看/收藏夹/带追踪参数的 B 站链接先规范化成标准 /video/BVxxx 形式，
        # 后续校验和 yt-dlp 下载拿到的都是干净链接
        if isinstance(data, dict) and data.get("platform") == "bilibili" and data.get("video_url"):
            data["video_url"] = normalize_video_url(str(data["video_url"]))
        return data

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)

        return v


NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
UPLOAD_DIR = "uploads"

# 任务级自动重试：首次 + NOTE_MAX_RETRIES 次重试（spec §7）
NOTE_MAX_RETRIES = int(os.getenv("NOTE_MAX_RETRIES", "3"))
NOTE_RETRY_BACKOFF = [5, 15, 45]  # 秒，指数退避


# 进行中状态：这些状态下不允许对同一视频重复提交（否则并发互踩，见 spec 001 §12）
_IN_FLIGHT_STATUSES = {
    TaskStatus.PENDING.value,
    TaskStatus.PARSING.value,
    TaskStatus.DOWNLOADING.value,
    TaskStatus.TRANSCRIBING.value,
    TaskStatus.SUMMARIZING.value,
    TaskStatus.FORMATTING.value,
    TaskStatus.SAVING.value,
}


def _get_task_record(video_id: str, platform: str):
    """返回 (task_id, status)；无记录/无状态文件时 status 为 None。"""
    if not video_id:
        return None, None
    try:
        task_id = get_task_by_video(video_id, platform)
    except Exception:
        logger.warning(f"查询去重记录失败 video_id={video_id}", exc_info=True)
        return None, None
    if not task_id:
        return None, None
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    if not os.path.exists(status_path):
        return task_id, None
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            return task_id, json.load(f).get("status")
    except Exception:
        return task_id, None


def _is_generated_task(video_id: str, platform: str) -> bool:
    """已成功生成过（spec 001 §6）。"""
    _, status = _get_task_record(video_id, platform)
    return status == TaskStatus.SUCCESS.value


def _is_task_in_flight(video_id: str, platform: str) -> bool:
    """是否有同一视频的任务正在跑（spec 001 §12：进行中也跳过，避免并发互踩）。"""
    _, status = _get_task_record(video_id, platform)
    return status in _IN_FLIGHT_STATUSES


def _expand_video_entry(bvid: str, title: str = "", duration: int = 0, cover: str = "") -> dict:
    """把一个视频展开成 video entry（含分P、去重标记、单条错误隔离）。"""
    try:
        parts = fetch_video_parts(bvid)
    except Exception as e:
        logger.warning(f"获取分P失败 bvid={bvid}: {e}")
        parts = []

    if not parts:
        return {
            "bvid": bvid,
            "title": title,
            "duration": duration,
            "cover": cover,
            "parts": [],
            "error": "未获取到分P信息（视频可能已删除或需要 Cookie）",
        }

    parts_count = len(parts)
    part_dicts = []
    for part in parts:
        video_id = build_video_id(bvid, part.p, parts_count)
        part_dicts.append({
            "p": part.p,
            "title": part.title,
            "duration": part.duration,
            "video_id": video_id,
            "url": build_video_url(bvid, part.p, parts_count),
            "already_generated": _is_generated_task(video_id, "bilibili"),
        })

    return {
        "bvid": bvid,
        "title": title or (parts[0].title if parts else ""),
        "duration": duration or sum(p.duration for p in parts),
        "cover": cover,
        "parts": part_dicts,
        "error": None,
    }


def _execute_note_with_retry(task_id: str, generator, execute_fn):
    """执行笔记任务；失败自动重试 NOTE_MAX_RETRIES 次（首次 + N 次重试）。"""
    for attempt in range(NOTE_MAX_RETRIES + 1):
        note = task_serial_executor.run(execute_fn)
        if note and getattr(note, "markdown", None):
            return note
        if attempt >= NOTE_MAX_RETRIES:
            logger.error(f"任务 {task_id} 重试 {NOTE_MAX_RETRIES} 次后仍失败")
            return None
        retry_no = attempt + 1
        delay = NOTE_RETRY_BACKOFF[min(attempt, len(NOTE_RETRY_BACKOFF) - 1)]
        logger.warning(
            f"任务 {task_id} 失败，第 {retry_no}/{NOTE_MAX_RETRIES} 次重试（{delay}s 后）"
        )
        try:
            generator._update_status(
                task_id, TaskStatus.PENDING,
                message=f"重试中 ({retry_no}/{NOTE_MAX_RETRIES})",
            )
        except Exception:
            pass
        if delay > 0:
            time.sleep(delay)
    return None


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)


def _persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    """把客户端预取的字幕写到 NoteGenerator 期望的转写缓存文件里。

    NoteGenerator.generate 会优先读 <task_id>_transcript.json，命中即跳过 download_subtitles
    与音频转写流程。要求字段：language(可空)/full_text/segments[{start,end,text}]
    """
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append({
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": text,
        })
    if not cleaned_segments:
        raise ValueError("prefetched_transcript 没有可用的 segments")

    full_text = transcript.get("full_text") or " ".join(s["text"] for s in cleaned_segments)
    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": full_text,
        "segments": cleaned_segments,
    }

    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    target = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_transcript.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[], sampling_mode="interval", max_frames=60
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    generator = NoteGenerator()

    def _execute_note_task():
        return generator.generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot,
            video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size,
            sampling_mode=sampling_mode,
            max_frames=max_frames,
        )

    logger.info(f"任务进入执行队列 (task_id={task_id})")
    note = _execute_note_with_retry(task_id, generator, _execute_note_task)
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)

    # 自动建立向量索引（用于 AI 问答），失败不影响笔记生成
    try:
        from app.services.vector_store import VectorStoreManager
        VectorStoreManager().index_task(task_id)
    except Exception as e:
        logger.warning(f"向量索引失败（不影响笔记）: {e}")


@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        # TODO: 待持久化完成
        # NoteGenerator().delete_note(video_id=data.video_id, platform=data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_location = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_location, "wb+") as f:
        f.write(await file.read())

    # 假设你静态目录挂载了 /uploads
    return R.success({"url": f"/uploads/{file.filename}"})


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:
        # 就绪门禁：本地转写引擎（fast-whisper / mlx-whisper）必须等模型下载完才能跑视频，
        # 否则任务会卡在首次下载（慢 / OOM / 截断），用户只看到一个静默失败的任务。
        # 客户端已抓好字幕（prefetched_transcript）则不需要转写，跳过检查。
        if not data.prefetched_transcript:
            from app.services.transcriber_config_manager import TranscriberConfigManager
            readiness = TranscriberConfigManager().is_model_ready()
            if not readiness["ready"]:
                logger.warning(f"拒绝 generate_note：{readiness['reason']}")
                return R.error(
                    msg=readiness["reason"],
                    code=300102,
                    data={
                        "reason": "transcriber_model_not_ready",
                        "transcriber_type": readiness["transcriber_type"],
                        "model_size": readiness["model_size"],
                        "downloading": readiness["downloading"],
                    },
                )

        video_id = extract_video_id(data.video_url, data.platform)

        # 同一视频正在生成时不再重复起任务（spec 001 §12）：
        # 并发跑同一视频会互踩 data/data/<id>.mp4 与抽帧目录。
        if not data.task_id and _is_task_in_flight(video_id, data.platform):
            return R.error(
                msg="该视频正在生成中，请稍候",
                code=300103,
                data={"reason": "task_in_progress"},
            )

        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        # 统一先写入 PENDING，表示已进入队列等待串行执行
        NoteGenerator()._update_status(task_id, TaskStatus.PENDING)

        # 客户端已经抓好字幕的话，写到转写缓存文件，NoteGenerator 的 cache-hit 逻辑会直接用上
        if data.prefetched_transcript:
            try:
                _persist_prefetched_transcript(task_id, data.prefetched_transcript)
            except Exception as e:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {e}")

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                                  data.extras, data.video_understanding, data.video_interval, data.grid_size,
                                  data.sampling_mode, data.max_frames)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExpandRequest(BaseModel):
    url: str


class BatchItem(BaseModel):
    bvid: str
    p: int = 1
    video_id: Optional[str] = None
    url: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    """批量生成请求（spec §5.2）。items 为前端勾选后的明确列表。"""

    platform: str = "bilibili"
    items: list[BatchItem]
    quality: DownloadQuality = DownloadQuality.fast
    model_name: str
    provider_id: str
    format: Optional[list] = []
    style: Optional[str] = None
    extras: Optional[str] = None
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    # spec 002：interval=固定间隔抽帧；smart=画面变化+字幕分段高价值抽帧
    sampling_mode: Optional[str] = "interval"
    max_frames: Optional[int] = 60


@router.post("/expand")
def expand(data: ExpandRequest):
    """两阶段流程第一阶段：把合集/多P 链接展开成可勾选的视频+分P 列表。"""
    try:
        url = (data.url or "").strip()
        if not url:
            return R.error(msg="链接不能为空", code=400)

        ref = parse_bilibili_collection_url(url)
        if ref:
            info = fetch_collection(ref["mid"], ref["sid"], ref["kind"])
            videos = [
                _expand_video_entry(v.bvid, v.title, v.duration, v.cover)
                for v in info.videos
            ]
            return R.success({
                "platform": "bilibili",
                "type": "collection",
                "title": info.title,
                "cover": info.cover,
                "owner": {"mid": info.owner_mid, "name": info.owner_name},
                "videos": videos,
            })

        bvid = extract_video_id(url, "bilibili")
        if not bvid:
            return R.error(msg="无法从链接中解析 BV 号", code=400)
        entry = _expand_video_entry(bvid)
        return R.success({
            "platform": "bilibili",
            "type": "video",
            "title": entry.get("title") or "",
            "cover": entry.get("cover") or "",
            "owner": {"mid": "", "name": ""},
            "videos": [entry],
        })
    except Exception as e:
        logger.error(f"展开失败: {e}", exc_info=True)
        return R.error(msg=f"展开失败: {e}")


@router.post("/generate_notes")
def generate_notes(data: BatchGenerateRequest, background_tasks: BackgroundTasks):
    """两阶段流程第二阶段：接收勾选列表，去重后逐条入队。"""
    try:
        if not data.model_name or not data.provider_id:
            return R.error(msg="请选择模型和提供者", code=400)

        # 就绪门禁：与单条 /generate_note 保持一致
        from app.services.transcriber_config_manager import TranscriberConfigManager
        readiness = TranscriberConfigManager().is_model_ready()
        if not readiness["ready"]:
            logger.warning(f"拒绝 generate_notes：{readiness['reason']}")
            return R.error(
                msg=readiness["reason"],
                code=300102,
                data={
                    "reason": "transcriber_model_not_ready",
                    "transcriber_type": readiness["transcriber_type"],
                    "model_size": readiness["model_size"],
                    "downloading": readiness["downloading"],
                },
            )

        results = []
        for item in data.items:
            video_id = item.video_id or item.bvid

            if _is_generated_task(video_id, data.platform):
                results.append({
                    "video_id": video_id,
                    "status": "skipped",
                    "reason": "already_generated",
                })
                continue

            if _is_task_in_flight(video_id, data.platform):
                results.append({
                    "video_id": video_id,
                    "status": "skipped",
                    "reason": "in_progress",
                })
                continue

            if item.url:
                note_url = item.url
            elif item.video_id and "_p" in item.video_id:
                note_url = f"https://www.bilibili.com/video/{item.bvid}?p={item.p}"
            else:
                note_url = f"https://www.bilibili.com/video/{item.bvid}"

            task_id = str(uuid.uuid4())
            NoteGenerator()._update_status(task_id, TaskStatus.PENDING)
            background_tasks.add_task(
                run_note_task, task_id, note_url, data.platform, data.quality, data.link,
                data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                data.extras, data.video_understanding, data.video_interval, data.grid_size,
                data.sampling_mode, data.max_frames,
            )
            results.append({"video_id": video_id, "task_id": task_id, "status": "queued"})

        return R.success({"results": results})
    except Exception as e:
        logger.error(f"批量生成失败: {e}", exc_info=True)
        return R.error(msg=f"批量生成失败: {e}")

@router.get("/task_status/{task_id}")
def get_task_status(task_id: str):
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.error(message or "任务失败", code=500)

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


@router.get("/image_proxy")
async def image_proxy(request: Request, url: str):
    headers = {
        "Referer": "https://www.bilibili.com/",
        "User-Agent": request.headers.get("User-Agent", ""),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail="图片获取失败")

            content_type = resp.headers.get("Content-Type", "image/jpeg")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  #  缓存一天
                    "Content-Type": content_type,
                }
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
