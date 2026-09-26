"""音频处理小工具：切割、压缩、时长探测、生成测试静音。

`compress_audio` 从原 GroqTranscriber 抽出；`split_audio` 供 OpenAI 兼容 ASR 声纹切割
（spec 003：过大的音频改为切割多段，而不是压缩）。
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import tempfile
import wave

import ffmpeg

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_COMPRESS_BITRATE = "64k"


def compress_audio(input_path: str, target_bitrate: str = DEFAULT_COMPRESS_BITRATE) -> str:
    """把音频压成 mp3，返回新的临时文件路径（调用方负责删除）。"""
    output_fd, output_path = tempfile.mkstemp(suffix=".mp3")
    os.close(output_fd)  # 关闭文件描述符，ffmpeg 会用路径操作
    ffmpeg.input(input_path).output(output_path, audio_bitrate=target_bitrate).run(
        quiet=True, overwrite_output=True
    )
    return output_path


def probe_duration_seconds(file_path: str) -> float:
    """探测音频时长（秒）；失败返回 0.0，不抛异常。"""
    try:
        return float(ffmpeg.probe(file_path, loglevel="quiet")["format"]["duration"])
    except Exception:
        return 0.0


def make_silent_wav(seconds: float = 1.0, sample_rate: int = 16000) -> str:
    """生成一段静音 wav，用于「测试连接」时做一次真实请求。"""
    output_fd, output_path = tempfile.mkstemp(suffix=".wav")
    os.close(output_fd)
    frame_count = int(sample_rate * seconds)
    with wave.open(output_path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frame_count)
    return output_path


def split_audio(input_path: str, segment_seconds: float) -> tuple[list[str], str]:
    """把音频按时间切成多段，**优先 stream copy 不重新编码**。

    返回 ``(chunk_paths, temp_dir)``；调用方负责删除 ``temp_dir``。
    某些容器（如 m4a）不支持 copy 切割时会退回按 64k 重新编码成 mp3。
    """
    if segment_seconds <= 0:
        segment_seconds = 600.0

    ext = os.path.splitext(input_path)[1].lower() or ".mp3"
    temp_dir = tempfile.mkdtemp(prefix="asr_chunks_")

    def _run(pattern: str, codec_args: list) -> list:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y",
            "-i", input_path,
            "-f", "segment",
            "-segment_time", f"{segment_seconds:.3f}",
            "-reset_timestamps", "1",
            *codec_args,
            pattern,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return sorted(glob.glob(os.path.join(temp_dir, "chunk_*")))

    # 先试无损切割
    try:
        chunks = _run(os.path.join(temp_dir, f"chunk_%03d{ext}"), ["-c", "copy"])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"stream copy 切割失败，将重新编码: {e}")
        chunks = []

    if len(chunks) <= 1:
        # copy 没切出来（格式不支持 / 只有一段）→ 清掉重来，按 mp3 重新编码切割
        for f in glob.glob(os.path.join(temp_dir, "chunk_*")):
            try:
                os.remove(f)
            except OSError:
                pass
        chunks = _run(
            os.path.join(temp_dir, "chunk_%03d.mp3"),
            ["-c:a", "libmp3lame", "-b:a", "64k"],
        )

    return chunks, temp_dir


# ---------------- 按「说话」自动切片（spec 003 追加） ----------------

_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def detect_speech_regions(
    input_path: str,
    noise_db: float = -30.0,
    min_silence: float = 0.5,
    timeout: int = 900,
) -> list:
    """用 ffmpeg silencedetect 找出「有人说话」的时间区间 [(start, end), ...]。

    失败 / 检测不到静音时返回 []，由调用方决定怎么退化。
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", input_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"静音检测失败: {e}")
        return []

    stderr = proc.stderr or ""
    starts = [float(x) for x in _SILENCE_START_RE.findall(stderr)]
    ends = [float(x) for x in _SILENCE_END_RE.findall(stderr)]
    duration = probe_duration_seconds(input_path)

    regions = []
    cursor = 0.0
    for idx, silence_start in enumerate(starts):
        if silence_start > cursor:
            regions.append((cursor, silence_start))
        cursor = ends[idx] if idx < len(ends) else silence_start
    if duration > 0 and cursor < duration:
        regions.append((cursor, duration))

    # 丢掉过短的碎片（<50ms）
    return [(a, b) for a, b in regions if b - a > 0.05]


def merge_regions_to_limit(regions: list, max_count: int = 120) -> list:
    """语音区间太多时，反复合并「空隙最小」的一对，直到不超过 max_count。

    合并只把相邻区间连起来，边界仍然落在真实静音处，不会凭空造时间点。
    """
    merged = [(float(a), float(b)) for a, b in regions]
    while len(merged) > max_count and len(merged) > 1:
        gaps = [(merged[i + 1][0] - merged[i][1], i) for i in range(len(merged) - 1)]
        _, idx = min(gaps)
        merged[idx] = (merged[idx][0], merged[idx + 1][1])
        del merged[idx + 1]
    return merged


def cut_audio_regions(input_path: str, regions: list) -> tuple:
    """按时间区间切出音频片段，返回 ([(start, end, path), ...], temp_dir)。

    优先 stream copy（不重编码）；个别格式不支持时退回按 64k 转 mp3。
    时间轴用**传进来的区间**，不依赖切出来的文件实际时长。
    """
    ext = os.path.splitext(input_path)[1].lower() or ".mp3"
    temp_dir = tempfile.mkdtemp(prefix="asr_speech_")
    out = []

    def _cut(start: float, end: float, target: str, codec_args: list) -> bool:
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y",
            "-ss", f"{start:.3f}", "-i", input_path,
            "-t", f"{max(0.05, end - start):.3f}",
            *codec_args, target,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return os.path.exists(target) and os.path.getsize(target) > 0
        except Exception:  # noqa: BLE001
            return False

    for idx, (start, end) in enumerate(regions):
        path = os.path.join(temp_dir, f"chunk_{idx:04d}{ext}")
        if not _cut(start, end, path, ["-c", "copy"]):
            path = os.path.join(temp_dir, f"chunk_{idx:04d}.mp3")
            if not _cut(start, end, path, ["-c:a", "libmp3lame", "-b:a", "64k"]):
                continue
        out.append((float(start), float(end), path))

    return out, temp_dir
