"""spec 002 ticket 09 追加：最后一组不足时也要出图，不能丢帧。

原来 `run()` 会把「不足 拼图格数」的那组直接跳过；5 张帧 + 2x2 会白丢 1 张。
现在按实际张数收缩行数，「半张」也拼出来。
"""
from PIL import Image

from app.utils.video_reader import VideoReader


def _make_frames(frame_dir, count: int):
    frame_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        Image.new("RGB", (320, 180), (i * 30, 80, 160)).save(
            frame_dir / f"frame_00_{i:02d}.jpg", quality=80
        )


def test_partial_last_group_produces_half_grid(tmp_path):
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    _make_frames(frame_dir, 5)

    reader = VideoReader(
        video_path="v.mp4", grid_size=(2, 2),
        frame_dir=str(frame_dir), grid_dir=str(grid_dir),
    )

    groups = reader.group_images()
    assert [len(g) for g in groups] == [4, 1]

    paths = []
    for idx, group in enumerate(groups, start=1):
        out = reader.concat_images(group, f"grid_{idx}")
        if out:
            paths.append(out)

    # 两张拼图都要有：整张 + 只含 1 帧的「半张」
    assert len(paths) == 2
    assert Image.open(paths[0]).size == (1920, 1080)
    assert Image.open(paths[1]).size == (1920, 540)


def test_exact_multiple_has_no_partial_grid(tmp_path):
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    _make_frames(frame_dir, 4)

    reader = VideoReader(
        video_path="v.mp4", grid_size=(2, 2),
        frame_dir=str(frame_dir), grid_dir=str(grid_dir),
    )

    groups = reader.group_images()
    assert [len(g) for g in groups] == [4]
    out = reader.concat_images(groups[0], "grid_1")
    assert Image.open(out).size == (1920, 1080)
