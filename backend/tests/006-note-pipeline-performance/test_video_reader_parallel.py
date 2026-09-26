"""spec 006 ticket 02：拼图 / 图像编码阶段的并发 + 进度分母真实性。

要点：
  * 编码结果顺序必须与入参一致（LLM 看到的图序不能乱）；
  * 网格图拼接确实并发执行，且结果顺序不乱；
  * building_grids 的分母 = 网格组数 + 帧数，全程不回退，并且一定走到 100%。
"""
import base64
import os
import threading
import time
from pathlib import Path

from PIL import Image

from app.utils.video_reader import VideoReader


def _make_jpg(path, color):
    Image.new("RGB", (60, 34), color).save(str(path), "JPEG")
    return str(path)


def _reader(tmp_path, **kwargs):
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"
    frame_dir.mkdir(exist_ok=True)
    grid_dir.mkdir(exist_ok=True)
    kwargs.setdefault("video_path", str(tmp_path / "fake.mp4"))
    return VideoReader(frame_dir=str(frame_dir), grid_dir=str(grid_dir), **kwargs)


def _decode(url: str) -> bytes:
    return base64.b64decode(url.split(",", 1)[1])


def test_encode_images_keeps_input_order_and_reports(tmp_path):
    reader = _reader(tmp_path)
    paths = [_make_jpg(tmp_path / f"g{i}.jpg", (i * 30, 0, 0)) for i in range(5)]
    reports = []

    urls = reader.encode_images_to_base64(
        paths, report=lambda done, total: reports.append((done, total))
    )

    assert [_decode(url) for url in urls] == [open(p, "rb").read() for p in paths]
    assert reports == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]
    assert reader.encode_images_to_base64([]) == []


def test_concat_images_writes_grid_file(tmp_path):
    reader = _reader(tmp_path, grid_size=(3, 2))
    paths = [_make_jpg(tmp_path / f"f{i}.jpg", (0, i * 40, 0)) for i in range(4)]

    out = reader.concat_images(paths, "grid_1")

    assert out and os.path.exists(out)
    assert os.path.basename(out) == "grid_1.jpg"
    with Image.open(out) as img:
        # 4 张 / 3 列 → 2 行；每格 unit_width x unit_height
        assert img.size == (reader.unit_width * 3, reader.unit_height * 2)


def test_concat_images_skips_unreadable_frames(tmp_path):
    reader = _reader(tmp_path)
    good = _make_jpg(tmp_path / "frame_00_00.jpg", (10, 10, 10))
    broken = tmp_path / "frame_00_01.jpg"
    broken.write_bytes(b"not-an-image")

    out = reader.concat_images([good, str(broken)], "grid_1")

    assert out and os.path.exists(out)


def test_run_concats_grids_concurrently_in_order(tmp_path, monkeypatch):
    reader = _reader(tmp_path)
    groups = [[_make_jpg(tmp_path / f"a{i}.jpg", (0, 0, 20 * i))] for i in range(4)]
    monkeypatch.setattr(reader, "extract_frames", lambda *a, **k: [])
    monkeypatch.setattr(reader, "group_images", lambda: groups)

    lock = threading.Lock()
    state = {"running": 0, "peak": 0}

    def fake_concat(image_paths, name):
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        time.sleep(0.05)
        path = os.path.join(reader.grid_dir, f"{name}.bin")
        with open(path, "wb") as fh:
            fh.write(name.encode())
        with lock:
            state["running"] -= 1
        return path

    monkeypatch.setattr(reader, "concat_images", fake_concat)

    urls = reader.run()

    assert state["peak"] >= 2, "多组网格图应该并发拼接"
    assert [_decode(url) for url in urls] == [b"grid_1", b"grid_2", b"grid_3", b"grid_4"]


def test_run_reports_monotonic_building_grids_until_100(tmp_path, monkeypatch):
    reader = _reader(tmp_path)
    # run() 开头会清空 frame_* 文件，所以帧必须在 extract_frames 里真正落盘
    def fake_extract_frames(*args, **kwargs):
        return [
            _make_jpg(Path(reader.frame_dir) / f"frame_00_0{i}.jpg", (10 * i, 10, 10))
            for i in range(4)
        ]

    monkeypatch.setattr(reader, "extract_frames", fake_extract_frames)

    reports = []
    reader.progress_callback = lambda stage, current=None, total=None, message="": reports.append(
        (stage, current, total)
    )

    urls = reader.run()

    assert len(urls) == 1
    grid_reports = [(current, total) for stage, current, total in reports if stage == "building_grids"]
    assert grid_reports, "building_grids 阶段必须上报进度"
    currents = [current for current, _ in grid_reports]
    assert currents == sorted(currents), "进度不能回退"
    assert grid_reports[-1] == (5, 5), "分母 = 1 个网格组 + 4 帧，且必须报告到 100%"
