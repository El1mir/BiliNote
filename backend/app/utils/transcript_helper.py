"""字幕时间轴处理（spec 003 追加）。

部分 ASR（如小米 MiMo 的 ``chat/completions + input_audio`` 风格）只返回整段文字，
没有逐句时间轴；切割后每段各产生一个 ``[0, 段时长]`` 的粗粒度 segment。后果：

* 高价值采样的「字幕分段」几乎没有候选；
* 综合采样让 LLM 按字幕选帧时，它拿到的每行都是巨大的时间段，给不出有意义的时间点。

这里把「时间跨度很长、内部没有细分」的 segment 按标点切句，再按**字数比例插值**出
近似时间轴。它是估算，不是真实对齐，但比「整段只有一个时间点」可用得多。
"""
from __future__ import annotations

import re
from typing import Iterable, List

from app.models.transcriber_model import TranscriptSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 超过这个跨度、且内部没有细分的 segment 才需要插值（正规 verbose_json 的分段通常几秒）
DEFAULT_MIN_SEGMENT_SECONDS = 20.0
# 一个句子里最多多少字符，超过就硬切
_MAX_CHARS_PER_PIECE = 60
# 插值后最多保留多少段
DEFAULT_MAX_SEGMENTS = 800

_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def split_text_into_pieces(text: str, max_chars: int = _MAX_CHARS_PER_PIECE) -> List[str]:
    """按中英文标点切句；过长的句子再按长度硬切。"""
    pieces: List[str] = []
    for sentence in _SENTENCE_RE.findall(text or ""):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            pieces.append(sentence)
        else:
            pieces.extend(
                sentence[i:i + max_chars] for i in range(0, len(sentence), max_chars)
            )
    return pieces


def _densify_one(
    segment: TranscriptSegment, min_segment_seconds: float
) -> List[TranscriptSegment]:
    duration = float(segment.end or 0) - float(segment.start or 0)
    text = (segment.text or "").strip()
    if duration <= min_segment_seconds or not text:
        return [segment]

    pieces = split_text_into_pieces(text)
    if len(pieces) <= 1:
        return [segment]

    total_chars = sum(len(p) for p in pieces) or 1
    out: List[TranscriptSegment] = []
    cursor = float(segment.start or 0)
    for piece in pieces:
        span = duration * len(piece) / total_chars
        out.append(
            TranscriptSegment(
                start=round(cursor, 3),
                end=round(cursor + span, 3),
                text=piece,
            )
        )
        cursor += span
    return out


def densify_segments(
    segments: Iterable[TranscriptSegment],
    min_segment_seconds: float = DEFAULT_MIN_SEGMENT_SECONDS,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
) -> List[TranscriptSegment]:
    """把粗粒度字幕插值成近似逐句时间轴。

    正规 ASR（返回 ``verbose_json`` 分段）的分段本来就短，会原样返回。
    """
    source = list(segments or [])
    if not source:
        return []

    out: List[TranscriptSegment] = []
    for segment in source:
        out.extend(_densify_one(segment, min_segment_seconds))

    if len(out) == len(source):
        return source  # 没有任何一段需要插值

    # 段太多时按时间均匀抽稀，避免下游（prompt / 采样）被撑爆
    if max_segments and len(out) > max_segments:
        step = len(out) / max_segments
        out = [out[min(len(out) - 1, int(i * step))] for i in range(max_segments)]

    logger.info(
        f"字幕时间轴插值：{len(source)} 段 → {len(out)} 段"
        f"（原始分段跨度过大，已按标点+字数比例估算时间）"
    )
    return out
