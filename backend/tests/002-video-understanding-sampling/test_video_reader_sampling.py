"""spec 002 ticket 01：VideoReader 的采样模式分派。"""
from unittest import mock

from app.utils.video_reader import VideoReader


def test_smart_mode_calls_sampler_with_subtitle_starts():
    reader = VideoReader(
        video_path="v.mp4",
        sampling_mode="smart",
        max_frames=5,
        subtitle_starts=[1.0, 2.0],
    )
    with mock.patch(
        "app.utils.frame_sampler.select_smart_timestamps", return_value=[1, 2, 3]
    ) as sampler, \
         mock.patch.object(reader, "extract_frames") as extract, \
         mock.patch("app.utils.video_reader.os.listdir", return_value=[]):
        reader.run()

    sampler.assert_called_once()
    assert sampler.call_args.kwargs["max_frames"] == 5
    assert sampler.call_args.kwargs["max_per_second"] == 2
    assert sampler.call_args.kwargs["frame_limit_mode"] == "total"
    assert sampler.call_args.kwargs["subtitle_starts"] == [1.0, 2.0]
    extract.assert_called_once_with(timestamps=[1, 2, 3], max_frames=3)


def test_smart_mode_passes_custom_frames_per_second():
    reader = VideoReader(
        video_path="v.mp4",
        sampling_mode="smart",
        max_frames=5,
        frames_per_second=3,
    )
    with mock.patch(
        "app.utils.frame_sampler.select_smart_timestamps", return_value=[1, 2, 3]
    ) as sampler,          mock.patch.object(reader, "extract_frames"),          mock.patch("app.utils.video_reader.os.listdir", return_value=[]):
        reader.run()

    assert sampler.call_args.kwargs["max_per_second"] == 3


def test_smart_mode_passes_per_second_limit_mode():
    reader = VideoReader(
        video_path="v.mp4",
        sampling_mode="smart",
        frames_per_second=4,
        frame_limit_mode="per_second",
    )
    with mock.patch(
        "app.utils.frame_sampler.select_smart_timestamps", return_value=[1, 2, 3]
    ) as sampler,          mock.patch.object(reader, "extract_frames"),          mock.patch("app.utils.video_reader.os.listdir", return_value=[]):
        reader.run()

    assert sampler.call_args.kwargs["frame_limit_mode"] == "per_second"
    assert sampler.call_args.kwargs["max_per_second"] == 4


def test_interval_mode_does_not_call_sampler():
    reader = VideoReader(video_path="v.mp4", sampling_mode="interval")
    with mock.patch(
        "app.utils.frame_sampler.select_smart_timestamps"
    ) as sampler, \
         mock.patch.object(reader, "extract_frames") as extract, \
         mock.patch("app.utils.video_reader.os.listdir", return_value=[]):
        reader.run()

    sampler.assert_not_called()
    extract.assert_called_once_with()


def test_format_time_keeps_subsecond_precision():
    reader = VideoReader(video_path="v.mp4")
    assert reader.format_time(5) == "00_05"
    assert reader.format_time(5.0) == "00_05"
    # 同一秒的第 2 帧：追加毫秒，避免文件名冲突
    assert reader.format_time(5.9) == "00_05_900"
    assert reader.format_time(65.25) == "01_05_250"


def test_extract_time_from_filename_parses_subsecond():
    reader = VideoReader(video_path="v.mp4")
    assert reader.extract_time_from_filename("frame_00_05.jpg") == 5.0
    assert reader.extract_time_from_filename("frame_00_05_900.jpg") == 5.9
    assert reader.extract_time_from_filename("nope.jpg") == float("inf")


def test_smart_mode_disables_frame_md5_dedupe():
    """长静态画面（PPT / 口播课）不能被逐帧 MD5 去重删到只剩几张。"""
    smart = VideoReader(video_path="v.mp4", sampling_mode="smart")
    assert smart.dedupe_enabled is False
    interval = VideoReader(video_path="v.mp4", sampling_mode="interval")
    assert interval.dedupe_enabled is True
