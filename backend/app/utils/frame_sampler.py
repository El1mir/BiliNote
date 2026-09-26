"""高价值帧采样（spec 002）。

两路信号合并：
  1. 画面变化：ffmpeg `select='gt(scene,THRESH)'` + `showinfo`，取镜头切换时间点；
  2. 字幕分段：转写结果每个 segment 的起始时间。

合并后按时间排序；限制方式二选一：每秒上限（per_second）或全片总量上限（total，均匀降采样）。
"""
from __future__ import annotations

import re
import subprocess
from typing import Iterable, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_SCENE_THRESHOLD = 0.4

# 综合采样（hybrid）三路来源的配额比例：LLM 选帧 / 高价值 / 均匀
HYBRID_LLM_RATIO = 0.4
HYBRID_SMART_RATIO = 0.3
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


def _dedupe_by_second(timestamps: Iterable[float], max_per_second: int = 1) -> list:
    """按秒分桶：每秒最多保留 ``max_per_second`` 个候选，按时间排序返回。

    同一秒内的多个候选按**原始顺序**取前 N 个（subtitle/scene 候选本身就近似有序），
    这样 ``max_per_second=1`` 时保持历史行为（每秒只留第一个）。
    """
    # None / <=0 表示不做每秒上限（total 模式先收全部候选，再按总量降采样）
    limit = int(max_per_second) if max_per_second and int(max_per_second) > 0 else None
    buckets: dict[int, list] = {}
    seen: set = set()
    for ts in timestamps:
        if ts is None:
            continue
        try:
            value = float(ts)
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        # 精确去重（毫秒级）：画面变化与字幕分段常在同一时间点命中同一秒
        ms_key = int(round(value * 1000))
        if ms_key in seen:
            continue
        seen.add(ms_key)
        bucket = buckets.setdefault(int(value), [])
        if limit is None or len(bucket) < limit:
            bucket.append(value)
    result = []
    for key in sorted(buckets):
        result.extend(buckets[key])
    return result


def _uniform_timestamps(duration: float, count: int) -> list:
    """在 (0, duration) 内均匀取 count 个时间点（取内点，避开片头片尾黑帧/logo）。"""
    if count <= 0 or duration <= 0:
        return []
    step = duration / (count + 1)
    return [round(step * (i + 1), 3) for i in range(count)]


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
    max_per_second: int = 2,
    frame_limit_mode: str = "total",
    duration: float = 0.0,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list:
    """合并「画面变化」与「字幕分段」两路信号，返回最终抽帧时间点（秒）。

    限制方式**二选一**（只会有一个参数生效）：

    * ``frame_limit_mode="total"``（默认）：只用 ``max_frames``，
      收全部候选后按时间均匀降采样，是该视频（批量时每个视频各自）的总量上限；
    * ``frame_limit_mode="per_second"``：只用 ``max_per_second``，
      每秒最多保留 N 个候选，不做总量截断。

    :param duration: 视频时长（秒）。total 模式下候选不足时用它补均匀采样，保证整段覆盖。
    """
    scene_ts = detect_scene_timestamps(video_path, threshold=scene_threshold)
    sub_ts = list(subtitle_starts or [])
    merged_input = [*scene_ts, *sub_ts]

    if frame_limit_mode == "per_second":
        merged = _dedupe_by_second(merged_input, max_per_second=max_per_second)
        logger.info(
            f"高价值采样候选：场景 {len(scene_ts)} + 字幕 {len(sub_ts)} "
            f"→ 每秒上限 {max_per_second}，去重后 {len(merged)}"
        )
        result = merged
        logger.info(f"高价值采样最终抽帧 {len(result)} 帧（每秒上限 {max_per_second}）")
    else:
        merged = _dedupe_by_second(merged_input, max_per_second=None)
        logger.info(
            f"高价值采样候选：场景 {len(scene_ts)} + 字幕 {len(sub_ts)} "
            f"→ 去重后 {len(merged)}"
        )
        # 画面变化少 / 没字幕时（PPT、口播课）候选会非常少，
        # 用均匀采样补足到上限，否则 40 分钟的课可能只抽到几张。
        added = 0
        for _ in range(3):
            if duration <= 0 or len(merged) >= max_frames:
                break
            fillers = _uniform_timestamps(duration, max_frames - len(merged))
            if not fillers:
                break
            before = len(merged)
            merged = _dedupe_by_second([*merged, *fillers], max_per_second=None)
            added += len(merged) - before
            if len(merged) == before:
                break
        if added:
            logger.info(
                f"高价值候选不足，补充均匀采样 {added} 帧 → 候选 {len(merged)}"
            )
        result = _downsample_evenly(merged, max_frames)
        logger.info(f"高价值采样最终抽帧 {len(result)} 帧（全片上限 {max_frames}）")

    # 保留亚秒精度：同一秒可能保留多帧，不能用 int() 直接截断
    return [round(float(t), 3) for t in result]


def select_hybrid_timestamps(
    video_path: str,
    subtitle_starts: Optional[Iterable[float]] = None,
    llm_timestamps: Optional[Iterable[float]] = None,
    max_frames: int = 60,
    duration: float = 0.0,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
) -> list:
    """综合采样：**高价值帧 + 均匀采样 + LLM 按字幕选帧**，三路都取。

    配额（约 LLM 40% / 高价值 30% / 均匀 30%）：

    1. LLM 选的时间点先占 ``max_frames * 0.4``（它最懂内容，但可能漏掉画面变化）；
    2. 高价值（场景切换 + 字幕分段）占 ``max_frames * 0.3``；
    3. **其余名额全部用均匀采样铺满**，保证整段视频都有覆盖。

    某一路候选不够时，多出来的名额会自动让给均匀采样。
    """
    n = max(1, int(max_frames))
    scene_ts = detect_scene_timestamps(video_path, threshold=scene_threshold)
    smart = _dedupe_by_second([*scene_ts, *(subtitle_starts or [])], max_per_second=None)
    llm = _dedupe_by_second(llm_timestamps or [], max_per_second=None)

    if duration > 0:
        smart = [t for t in smart if 0 <= t <= duration]
        llm = [t for t in llm if 0 <= t <= duration]

    # 配额：至少给均匀采样留 1 个位置
    llm_quota = max(1, int(round(n * HYBRID_LLM_RATIO)))
    smart_quota = max(1, int(round(n * HYBRID_SMART_RATIO)))
    if llm_quota + smart_quota > n - 1:
        llm_quota = max(1, int((n - 1) * HYBRID_LLM_RATIO / (HYBRID_LLM_RATIO + HYBRID_SMART_RATIO)))
        smart_quota = max(0, n - 1 - llm_quota)

    picked = [
        *_downsample_evenly(llm, llm_quota),
        *_downsample_evenly(smart, smart_quota),
    ]
    merged = _dedupe_by_second(picked, max_per_second=None)

    # 剩余名额用均匀采样补满：先把均匀池做密，再排除掉已经落到的秒，
    # 否则取到的均匀点正好和 LLM / 高价值候选重合时会补不满。
    if duration > 0 and len(merged) < n:
        pool = _uniform_timestamps(duration, max(4 * n, n + 10))
        used_seconds = {int(round(t)) for t in merged}
        free = [t for t in pool if int(round(t)) not in used_seconds]
        fillers = _downsample_evenly(free, n - len(merged))
        if fillers:
            merged = _dedupe_by_second([*merged, *fillers], max_per_second=None)

    result = _downsample_evenly(merged, n)
    logger.info(
        f"综合采样：LLM {len(llm)} + 高价值(场景 {len(scene_ts)} / 字幕 "
        f"{len(list(subtitle_starts or []))}) → 合并后 {len(result)} 帧（上限 {n}）"
    )
    return [round(float(t), 3) for t in result]
