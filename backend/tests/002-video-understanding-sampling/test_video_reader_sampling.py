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
    assert sampler.call_args.kwargs["subtitle_starts"] == [1.0, 2.0]
    extract.assert_called_once_with(timestamps=[1, 2, 3])


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
