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


def test_select_total_mode_keeps_subsecond_precision():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[5.0, 10.4]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4", subtitle_starts=[1.0, 5.9, 20.0], max_frames=60
        )
    # 默认 total 模式：收全部候选，亚秒精度不被截断，未超上限不降采样
    assert out == [1.0, 5.0, 5.9, 10.4, 20.0]


def test_select_per_second_mode_caps_each_second():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[5.0, 5.4, 10.4]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4",
            subtitle_starts=[1.0, 5.9, 20.0],
            max_per_second=1,
            frame_limit_mode="per_second",
        )
    # per_second 模式：每秒只留第一个，且不做全片总量截断
    assert out == [1.0, 5.0, 10.4, 20.0]


def test_select_per_second_mode_ignores_max_frames():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[1.0, 2.0, 3.0, 4.0]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4",
            subtitle_starts=[],
            max_frames=2,
            max_per_second=1,
            frame_limit_mode="per_second",
        )
    # 二选一：per_second 模式下 max_frames 不生效
    assert out == [1.0, 2.0, 3.0, 4.0]


def test_select_total_mode_ignores_per_second():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[1.0, 1.4, 2.0, 3.0, 4.0]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4",
            subtitle_starts=[],
            max_frames=2,
            max_per_second=1,
            frame_limit_mode="total",
        )
    # 二选一：total 模式下每秒上限不生效，只按全片上限均匀降采样
    assert len(out) == 2
    assert out[0] == 1.0
    assert out[-1] == 4.0


def test_dedupe_by_second_max_per_second():
    raw = [1.1, 1.2, 1.3, 3.0, 3.4]
    assert frame_sampler._dedupe_by_second(raw, max_per_second=2) == [1.1, 1.2, 3.0, 3.4]
    assert frame_sampler._dedupe_by_second(raw, max_per_second=1) == [1.1, 3.0]


def test_dedupe_by_second_removes_exact_duplicates():
    # 画面变化与字幕分段可能在同一时间点命中，同秒上限 >1 时不能重复保留
    assert frame_sampler._dedupe_by_second([5.0, 5.0, 5.4, 5.4], max_per_second=2) == [5.0, 5.4]


def test_select_removes_scene_subtitle_exact_duplicate():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[5.0, 30.0]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4", subtitle_starts=[5.0, 30.0], max_frames=6, max_per_second=2
        )
    assert out == [5.0, 30.0]


def test_select_respects_max_frames():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=list(range(0, 200))
    ):
        out = frame_sampler.select_smart_timestamps("v.mp4", subtitle_starts=[], max_frames=20)
    assert len(out) == 20


def test_scene_detection_failure_returns_empty():
    with mock.patch("app.utils.frame_sampler.subprocess.run", side_effect=RuntimeError("boom")):
        assert frame_sampler.detect_scene_timestamps("v.mp4") == []


def test_select_fills_uniform_when_candidates_few():
    """画面变化少的课：候选不足时要均匀补点，保证整段都有覆盖。"""
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps", return_value=[20.0, 40.0]
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4", subtitle_starts=[], max_frames=10, duration=100.0
        )
    assert len(out) == 10
    assert min(out) < 20 and max(out) > 40  # 不再只有 20/40 两个点


def test_select_does_not_fill_when_candidates_enough():
    with mock.patch.object(
        frame_sampler, "detect_scene_timestamps",
        return_value=[float(i) for i in range(0, 50)],
    ):
        out = frame_sampler.select_smart_timestamps(
            "v.mp4", subtitle_starts=[], max_frames=10, duration=100.0
        )
    assert len(out) == 10
    # 没有补点：结果都来自场景候选（0..49），不会跑到 50+ 的均匀补点区
    assert max(out) < 50


def test_uniform_timestamps_take_interior_points():
    stamps = frame_sampler._uniform_timestamps(100.0, 4)
    assert len(stamps) == 4
    assert all(0 < s < 100 for s in stamps)
    assert stamps == sorted(stamps)
