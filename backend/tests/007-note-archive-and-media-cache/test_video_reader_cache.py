"""spec 007 ticket 04：视觉网格缓存的冷/热路径、失效与损坏恢复。

ticket 04 的验收条目此前一直标【待验证】。这里覆盖其中**可离线验证**的部分
（不依赖 ffmpeg / 真实视频 / 视觉模型）：抽帧用桩替换、帧文件直接预置，但拼图、
缓存写入、缓存读取、失效判定与清理全部走真实代码与真实文件系统。

覆盖：
* 冷路径拼图后写入缓存条目（含 metadata.txt）；
* 热路径命中缓存、**跳过拼图**，且返回的图像内容与冷路径一致；
* 视频内容变化 / 采样配置变化 / 网格布局变化 → cache miss；
* 缓存条目损坏（metadata 声明的文件缺失）→ 视为 miss 并重建；
* 条目过期（TTL 7 天）→ 不被复用，且被清理掉而不是永远留在磁盘上；
* 缓存按 task_id 隔离，别的任务不能命中我的条目。

**仍未验证**（本文件不声称通过）：真实视频的冷/热耗时基准、并发写入中断、
磁盘满场景。见 ticket 04「验收」里剩下的【待验证】条目。
"""

import os
import time
from pathlib import Path

from PIL import Image

import app.utils.video_reader as video_reader_module
from app.utils.video_reader import VideoReader


def _make_frames(frame_dir: Path, count: int) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        Image.new("RGB", (16, 9), (i * 20 % 255, 80, 160)).save(
            frame_dir / f"frame_00_{i:02d}.jpg", quality=80
        )


def _scene(
    tmp_path: Path,
    monkeypatch,
    *,
    frames: int = 4,
    grid_size=(2, 2),
    max_frames: int = 60,
    task_id: str = "task-1",
    video_bytes: bytes = b"video-1",
):
    """搭一个「帧已抽好」的现场并返回 VideoReader。

    视频文件只写一次（同一次测试内多次调用 _scene 时复用），否则 mtime 变化会
    让指纹变化，把本该命中缓存的第二次调用变成 miss —— 那是测试自己的假象。

    帧**不能**在调用 run() 之前预置：run() 开头会清掉 frame_dir 里的 frame_*，
    这正是 ticket 04 已知的「当前仍重做视频抽帧」。所以抽帧用桩替代，由桩在
    清空之后再把帧写出来，等价于「抽帧完成」，且不需要 ffmpeg 与真实视频。
    """
    video = tmp_path / "video.mp4"
    if not video.exists():
        video.write_bytes(video_bytes)
    frame_dir = tmp_path / "frames"
    grid_dir = tmp_path / "grids"

    monkeypatch.setattr(
        video_reader_module,
        "get_app_dir",
        lambda subdir="": str(tmp_path / "app" / subdir),
    )
    # (0, 100) = 不设字节上限，避免本测试的条目被 LRU 裁掉干扰断言。
    monkeypatch.setattr(video_reader_module, "_visual_cache_limits", lambda: (0, 100))

    reader = VideoReader(
        video_path=str(video),
        task_id=task_id,
        grid_size=grid_size,
        max_frames=max_frames,
        unit_width=32,
        unit_height=18,
        frame_dir=str(frame_dir),
        grid_dir=str(grid_dir),
    )
    monkeypatch.setattr(
        reader,
        "extract_frames",
        lambda **kwargs: _make_frames(Path(reader.frame_dir), frames),
    )
    return reader


def _cache_root(reader: VideoReader) -> Path:
    """`_grid_cache_dir()` 对无 task_id 的实例返回 None；这里断言本测试始终有 task_id。"""
    cache_dir = reader._grid_cache_dir()
    assert cache_dir is not None, "本测试的 VideoReader 必须带 task_id"
    return Path(cache_dir)


def _cache_entry(reader: VideoReader) -> Path:
    cache_root = _cache_root(reader)
    metas = list(cache_root.rglob("metadata.txt"))
    assert len(metas) == 1, f"期望恰好 1 个缓存条目，实际 {len(metas)}"
    return metas[0].parent


def test_visual_grid_cache_requires_task_scope_and_fingerprint(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video payload")
    monkeypatch.setattr(
        video_reader_module, "get_app_dir", lambda subdir="": str(tmp_path / subdir)
    )
    reader = VideoReader(
        video_path=str(video), task_id="task-1", max_frames=12, grid_size=(3, 2)
    )
    assert _cache_root(reader).name == "v1"
    groups = [[str(tmp_path / "frame_00_01.jpg")]]
    first_key = reader._grid_cache_key(groups)
    reader.max_frames = 13
    assert reader._grid_cache_key(groups) != first_key
    reader_without_task = VideoReader(video_path=str(video))
    assert reader_without_task._grid_cache_dir() is None


def test_visual_grid_key_changes_when_video_content_changes(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"first version")
    reader = VideoReader(video_path=str(video), task_id="task-1")
    before = reader._grid_cache_key([])
    video.write_bytes(b"second version")
    assert reader._grid_cache_key([]) != before


def test_cold_path_writes_entry_and_hot_path_reuses_it(tmp_path, monkeypatch):
    cold_reader = _scene(tmp_path, monkeypatch)
    cold_urls = cold_reader.run()
    assert cold_reader._cache_hit is False
    assert len(cold_urls) == 1  # 4 帧 / (2x2) = 1 个网格

    entry = _cache_entry(cold_reader)
    assert (entry / "metadata.txt").read_text(encoding="utf-8") == "1"
    assert (entry / "grid_1.jpg").is_file()

    hot_reader = _scene(tmp_path, monkeypatch)
    # 热路径必须跳过拼图：把 concat_images 换成会爆炸的桩来证明它没被调用。
    monkeypatch.setattr(
        hot_reader,
        "concat_images",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("热路径不应重新拼图")),
    )
    hot_urls = hot_reader.run()
    assert hot_reader._cache_hit is True
    # 热路径复用同一批网格文件 → 编码结果必须逐字节一致。
    assert hot_urls == cold_urls


def test_cache_miss_when_video_content_changes(tmp_path, monkeypatch):
    first = _scene(tmp_path, monkeypatch)
    first.run()
    assert first._cache_hit is False

    # 同路径、不同内容：指纹变化必须导致 miss。
    (tmp_path / "video.mp4").write_bytes(b"video-2")
    second = _scene(tmp_path, monkeypatch)
    second.run()
    assert second._cache_hit is False


def test_cache_miss_when_sampling_config_changes(tmp_path, monkeypatch):
    base = _scene(tmp_path, monkeypatch, max_frames=60)
    base.run()
    changed = _scene(tmp_path, monkeypatch, max_frames=13)
    changed.run()
    assert changed._cache_hit is False


def test_cache_miss_when_grid_layout_changes(tmp_path, monkeypatch):
    base = _scene(tmp_path, monkeypatch, frames=4, grid_size=(2, 2))
    base.run()
    changed = _scene(tmp_path, monkeypatch, frames=4, grid_size=(4, 1))
    changed.run()
    assert changed._cache_hit is False


def test_corrupt_cache_entry_is_treated_as_miss_and_rebuilt(tmp_path, monkeypatch):
    reader = _scene(tmp_path, monkeypatch)
    reader.run()
    entry = _cache_entry(reader)
    # metadata 声称有 1 张，但文件被删掉 → 不能当命中。
    (entry / "grid_1.jpg").unlink()

    rebuilt = _scene(tmp_path, monkeypatch)
    rebuilt.run()
    assert rebuilt._cache_hit is False
    assert (entry / "grid_1.jpg").is_file()


def test_expired_cache_entry_is_not_reused_and_is_cleaned(tmp_path, monkeypatch):
    first = _scene(tmp_path, monkeypatch)
    first.run()
    entry = _cache_entry(first)

    stale = time.time() - 8 * 24 * 3600  # TTL 是 7 天
    os.utime(entry, (stale, stale))

    again = _scene(tmp_path, monkeypatch)
    urls = again.run()
    assert again._cache_hit is False
    assert len(urls) == 1  # 过期不影响正确性，只是重新拼图
    # 过期条目被清掉，而不是被复用、也不是永远占着磁盘。
    assert not entry.exists()


def test_cache_entries_are_isolated_per_task(tmp_path, monkeypatch):
    task_a = _scene(tmp_path, monkeypatch, task_id="task-a")
    task_a.run()

    task_b = _scene(tmp_path, monkeypatch, task_id="task-b")
    task_b.run()
    assert task_b._cache_hit is False, "别的任务的条目不能被命中"

    task_a_again = _scene(tmp_path, monkeypatch, task_id="task-a")
    task_a_again.run()
    assert task_a_again._cache_hit is True
