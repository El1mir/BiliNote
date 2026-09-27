from pathlib import Path

import app.utils.video_reader as video_reader_module
from app.utils.video_reader import VideoReader


def test_visual_grid_cache_requires_task_scope_and_fingerprint(monkeypatch, tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video payload')
    monkeypatch.setattr(video_reader_module, 'get_app_dir', lambda subdir='': str(tmp_path / subdir))
    reader = VideoReader(video_path=str(video), task_id='task-1', max_frames=12, grid_size=(3, 2))
    assert Path(reader._grid_cache_dir()).name == 'v1'
    groups = [[str(tmp_path / 'frame_00_01.jpg')]]
    first_key = reader._grid_cache_key(groups)
    reader.max_frames = 13
    assert reader._grid_cache_key(groups) != first_key
    reader_without_task = VideoReader(video_path=str(video))
    assert reader_without_task._grid_cache_dir() is None


def test_visual_grid_key_changes_when_video_content_changes(tmp_path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'first version')
    reader = VideoReader(video_path=str(video), task_id='task-1')
    before = reader._grid_cache_key([])
    video.write_bytes(b'second version')
    assert reader._grid_cache_key([]) != before


