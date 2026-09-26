"""真实视频回归：画面变化极少的长视频也要抽到接近上限的帧数。

对应问题：40 分钟课程只抽到 3 张（场景候选少 + 逐帧 MD5 去重把静态画面删光）。
"""
import os
import subprocess

import pytest

from app.utils.video_reader import VideoReader


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="需要 ffmpeg")


def _make_static_video(path: str, seconds: int = 30) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=gray:s=320x180:d={seconds}:r=5",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", path,
        ],
        check=True,
        capture_output=True,
    )


def test_smart_sampling_covers_nearly_static_video(tmp_path):
    video = tmp_path / "static.mp4"
    _make_static_video(str(video), seconds=30)

    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    VideoReader(
        video_path=str(video),
        grid_size=(2, 2),
        sampling_mode="smart",
        max_frames=20,
        frame_dir=str(frame_dir),
        grid_dir=str(grid_dir),
    ).run()

    frames = [f for f in os.listdir(frame_dir) if f.startswith("frame_")]
    # 旧的逐帧 MD5 去重会把几乎静止的画面删到 1~2 张；现在应接近上限
    assert len(frames) >= 15


def test_smart_sampling_produces_frames_spanning_whole_video(tmp_path):
    video = tmp_path / "static.mp4"
    _make_static_video(str(video), seconds=30)

    frame_dir = tmp_path / "frames2"
    grid_dir = tmp_path / "grids2"
    reader = VideoReader(
        video_path=str(video),
        grid_size=(2, 2),
        sampling_mode="smart",
        max_frames=10,
        frame_dir=str(frame_dir),
        grid_dir=str(grid_dir),
    )
    reader.run()

    names = [f for f in os.listdir(frame_dir) if f.startswith("frame_")]
    assert len(names) >= 8
    times = sorted(reader.extract_time_from_filename(n) for n in names)
    # 时间戳应铺满整段（30s），而不是挤在某几秒
    assert times[0] < 8
    assert times[-1] > 22
