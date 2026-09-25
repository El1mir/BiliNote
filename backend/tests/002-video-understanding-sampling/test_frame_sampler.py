"""spec 002 ticket 01：高价值帧采样算法。"""
from unittest import mock

from app.utils import frame_sampler


def test_dedupe_by_second_sorts_and_filters():
    raw = [3.2, 1.9, 3.9, 1.1, -2.0, None, "bad"]
    assert frame_sampler._dedupe_by_second(raw) == [1.9, 3.2]


def test_downsample_evenly_caps_and_keeps_ends():
    out = frame_sampler._downsample_evenly(list(range(100)), 10)
    assert len(out) == 10
    assert out[0] == 0
    assert out[-1] == 99


def test_downsample_noop_when_under_cap():
    assert frame_sampler._downsample_evenly([1, 2, 3], 10) == [1, 2, 3]


def test_select_merges_scene_and_subtitle_then_dedupes():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[5.0, 10.4]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4", subtitle_starts=[1.0, 5.9, 20.0], max_frames=60
        )
    # 5.0 与 5.9 落在同一秒 → 去重
    assert out == [1, 5, 10, 20]


def test_select_respects_max_frames():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=list(range(0, 200))
    ):
        out = frame_sampler.select_smart_timestamps("v.mp4", subtitle_starts=[], max_frames=20)
    assert len(out) == 20


def test_scene_detection_failure_returns_empty():
    with mock.patch("app.utils.frame_sampler.subprocess.run", side_effect=RuntimeError("boom")):
        assert frame_sampler.detect_scene_timestamps("v.mp4") == []
