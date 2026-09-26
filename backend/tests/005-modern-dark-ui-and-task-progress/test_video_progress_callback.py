from unittest.mock import Mock

from app.utils.video_reader import VideoReader


def test_video_reader_reports_frame_progress(tmp_path):
    callback = Mock()
    reader = VideoReader(
        video_path="video.mp4",
        frame_dir=str(tmp_path / "frames"),
        progress_callback=callback,
    )

    def fake_extract(ts):
        path = tmp_path / "frames" / f"frame-{ts}.jpg"
        path.write_bytes(str(ts).encode())
        return str(path)

    reader._extract_single_frame = Mock(side_effect=fake_extract)
    reader._calculate_file_md5 = Mock(side_effect=lambda path: path)

    paths = reader.extract_frames(max_frames=2, timestamps=[1.0, 2.0])

    assert len(paths) == 2
    stages = [call.args[0] for call in callback.call_args_list]
    assert stages == ["extracting_frames", "extracting_frames"]
    assert callback.call_args_list[-1].kwargs["current"] == 2
    assert callback.call_args_list[-1].kwargs["total"] == 2


def test_video_reader_reports_grid_progress(tmp_path):
    callback = Mock()
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    frame_dir.mkdir()
    reader = VideoReader(
        video_path="video.mp4",
        grid_size=(2, 2),
        frame_dir=str(frame_dir),
        grid_dir=str(grid_dir),
        progress_callback=callback,
    )
    reader.extract_frames = Mock()
    reader.group_images = Mock(return_value=[["a"], ["b"]])
    reader.concat_images = Mock(side_effect=lambda group, name: f"grid-{name}")

    def fake_encode(paths, report=None):
        if report:
            report(1, len(paths))
            report(2, len(paths))
        return ["encoded-a", "encoded-b"]

    reader.encode_images_to_base64 = Mock(side_effect=fake_encode)

    assert reader.run() == ["encoded-a", "encoded-b"]
    grid_calls = [call for call in callback.call_args_list if call.args[0] == "building_grids"]
    values = [(call.kwargs["current"], call.kwargs["total"]) for call in grid_calls]
    # 分母 = 2 个网格组 + 2 张待编码图像；进度不能回退，且必须走到 100%
    assert values[-1] == (4, 4)
    assert [current for current, _ in values] == sorted(current for current, _ in values)


def test_grid_stage_reaches_100_even_if_encoder_is_silent(tmp_path):
    """编码回调缺失（或异常安静）时，阶段也必须收尾到 100%，不能卡在中间百分比。"""
    callback = Mock()
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    frame_dir.mkdir()
    reader = VideoReader(
        video_path="video.mp4",
        grid_size=(2, 2),
        frame_dir=str(frame_dir),
        grid_dir=str(grid_dir),
        progress_callback=callback,
    )
    reader.extract_frames = Mock()
    reader.group_images = Mock(return_value=[["a"], ["b"]])
    reader.concat_images = Mock(return_value="grid-a")
    reader.encode_images_to_base64 = Mock(return_value=["encoded-a"])

    reader.run()

    grid_calls = [call for call in callback.call_args_list if call.args[0] == "building_grids"]
    assert grid_calls[-1].kwargs["current"] == grid_calls[-1].kwargs["total"] == 4
