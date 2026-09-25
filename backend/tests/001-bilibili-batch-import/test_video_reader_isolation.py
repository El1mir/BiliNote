"""spec 001 §12 / ticket 08：VideoReader 实例级目录隔离与清理。"""
import os

from app.utils.video_reader import VideoReader


def test_each_instance_gets_unique_dirs():
    a = VideoReader(video_path="x.mp4")
    b = VideoReader(video_path="x.mp4")

    assert a.frame_dir != b.frame_dir
    assert a.grid_dir != b.grid_dir
    # 并发任务不再共用全局目录
    assert os.path.isdir(a.frame_dir)
    assert os.path.isdir(b.frame_dir)


def test_cleanup_removes_auto_created_dirs():
    reader = VideoReader(video_path="x.mp4")
    frame_dir, grid_dir = reader.frame_dir, reader.grid_dir

    reader._cleanup_temp_dirs()

    assert not os.path.isdir(frame_dir)
    assert not os.path.isdir(grid_dir)


def test_cleanup_keeps_explicitly_passed_dirs(tmp_path):
    reader = VideoReader(
        video_path="x.mp4",
        frame_dir=str(tmp_path),
        grid_dir=str(tmp_path),
    )

    reader._cleanup_temp_dirs()

    assert os.path.isdir(str(tmp_path))
