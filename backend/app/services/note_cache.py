"""共享的流水线 JSON 缓存接缝（spec 017 ticket 004）。

生成链路会为每个任务缓存三类中间产物 —— 音频元信息、转写结果、画面判定/OCR 结果。
原先每个阶段各自写了一份「读文件 → json.loads → 重建 dataclass」的代码，而且已经跑偏：
三处读转写缓存里，两处用 ``data.get("language")`` 容忍缺字段，第三处用 ``data["language"]``
直接 KeyError —— 同一个缓存文件，先被哪个阶段读到决定了任务是继续还是崩。

这里收成一条缝，一条策略：

- 读取永远防御式：文件不存在、JSON 坏了、字段缺了、类型不对，一律当缓存未命中返回 ``None``，
  由调用方回退到重算。坏缓存是 miss，不是任务失败。
- 写入永远原子且 ``ensure_ascii=False``，中文标题/正文在缓存里保持可读。
- 缓存格式只在这里定义，字段增删不再需要同步改三处。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)


def shared_transcript_path(base_dir: Path, video_url: str, engine_key: str) -> Path:
    """跨任务共享转写缓存的位置：键是「哪个视频 + 哪个转写引擎」，不是 task_id。

    同一个视频换模型再生成时，下载与转写的结果和上一次逐字相同；带上引擎身份是因为
    换了 ASR 引擎或模型，同一段音频本来就该得出不同结果，复用它等于返回错误答案。
    """
    raw = f"{str(video_url).strip()}|{str(engine_key).strip()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return Path(base_dir) / "shared" / f"transcript_{digest}.json"


def read_json_cache(path: Path) -> dict | None:
    """把缓存文件读成 dict；任何异常都折算成「未命中」。"""
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # 坏缓存不是错误路径，只是 miss
        logger.warning(f"读取缓存失败（按未命中处理）{path}: {e}")
        return None
    return data if isinstance(data, dict) else None


def write_json_cache(path: Path, payload: Any) -> bool:
    """原子写缓存：先写同目录临时文件再 replace，避免半截 JSON 被下一个任务读到。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(temp_name, path)
        except Exception:
            # 临时文件清不掉只是留一份垃圾，不该盖住真正的写入错误。
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
            raise
        return True
    except Exception as e:
        logger.warning(f"写入缓存失败（不影响任务结果）{path}: {e}")
        return False


def read_transcript_cache(path: Path) -> TranscriptResult | None:
    """读转写缓存；缺 language/segments 或缺 full_text 都按未命中处理。"""
    data = read_json_cache(path)
    if not data:
        return None
    full_text = data.get("full_text")
    if not isinstance(full_text, str):
        return None
    segments = []
    for raw in data.get("segments") or []:
        try:
            segments.append(TranscriptSegment(**raw))
        except Exception:
            # 单段坏数据不该让整份缓存作废，但也不能静默吞掉转写内容
            logger.warning(f"转写缓存中存在无法解析的片段，已跳过：{raw!r}")
    return TranscriptResult(
        language=data.get("language"),
        full_text=full_text,
        segments=segments,
    )


def write_transcript_cache(path: Path, transcript: TranscriptResult) -> bool:
    return write_json_cache(path, asdict(transcript))


def read_audio_cache(path: Path, *, require_file: bool = True) -> AudioDownloadResult | None:
    """读音频元信息缓存。

    ``require_file=True``（默认）时会校验缓存里记的文件是否还在：媒体清理会按容量/过期
    删掉音频，只认缓存不认文件的话，任务会拿着已经不存在的路径去转写，报出误导性的
    「No such file or directory」。
    """
    data = read_json_cache(path)
    if not data:
        return None
    try:
        cached = AudioDownloadResult(**data)
    except Exception as e:
        logger.warning(f"音频缓存字段不完整，将重新下载：{e}")
        return None
    if require_file and cached.file_path and not Path(cached.file_path).is_file():
        logger.warning(f"音频缓存已失效（文件不存在：{cached.file_path}），将重新下载")
        return None
    return cached


def write_audio_cache(path: Path, audio: AudioDownloadResult) -> bool:
    return write_json_cache(path, asdict(audio))
