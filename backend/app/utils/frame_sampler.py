"""高价值帧采样（spec 002）。

两路信号合并：
  1. 画面变化：ffmpeg `select='gt(scene,THRESH)'` + `showinfo`，取镜头切换时间点；
  2. 字幕分段：转写结果每个 segment 的起始时间。

合并后按秒去重、按时间排序，超过上限时按时间均匀降采样。
"""
from __future__ import annotations

import re
import subprocess
from typing import Iterable, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SCENE_THRESHOLD = 0.4
_PTS_TIME_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def detect_scene_timestamps(
    video_path: str,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    timeout: int = 600,
) -> list:
    """用 ffmpeg scene detection 找出画面变化剧烈的时间点（秒）。失败返回 []。"""
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-an", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - 采样失败不应让任务挂掉
        logger.warning(f"场景检测失败: {e}")
        return []

    # showinfo 把 "pts_time:12.345" 打在 stderr
    stamps = []
    for raw in _PTS_TIME_RE.findall(proc.stderr or ""):
        try:
            stamps.append(float(raw))
        except ValueError:
            continue
    logger.info(f"场景检测到 {len(stamps)} 个候选时间点")
    return stamps


def _dedupe_by_second(timestamps: Iterable[float]) -> list:
    """按秒去重并排序（同一秒只保留一个）。"""
    buckets = {}
    for ts in timestamps:
        if ts is None:
            continue
        try:
            value = float(ts)
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        buckets.setdefault(int(value), value)
    return [buckets[k] for k in sorted(buckets)]


def _downsample_evenly(items: list, max_frames: int) -> list:
    """超过上限时按时间均匀降采样，保留首尾。"""
    if max_frames <= 0 or len(items) <= max_frames:
        return items
    if max_frames == 1:
        return [items[0]]
    # 含首尾的均匀采样：step 按 max_frames-1 段切分
    step = (len(items) - 1) / float(max_frames - 1)
    picked = [items[int(round(i * step))] for i in range(max_frames)]
    # 去重（极端情况下可能重复）
    seen = set()
    result = []
    for ts in picked:
        if ts not in seen:
            seen.add(ts)
            result.append(ts)
    return result


def select_smart_timestamps(
    video_path: str,
    subtitle_starts: Optional[Iterable[float]] = None,
    max_frames: int = 60,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list:
    """合并「画面变化」与「字幕分段」两路信号，返回最终抽帧时间点（秒）。"""
    scene_ts = detect_scene_timestamps(video_path, threshold=scene_threshold)
    sub_ts = list(subtitle_starts or [])

    merged = _dedupe_by_second([*scene_ts, *sub_ts])
    logger.info(
        f"高价值采样候选：场景 {len(scene_ts)} + 字幕 {len(sub_ts)} → 去重后 {len(merged)}"
    )

    result = _downsample_evenly(merged, max_frames)
    logger.info(f"高价值采样最终抽帧 {len(result)} 帧（上限 {max_frames}）")
    return [int(round(t)) for t in result]
