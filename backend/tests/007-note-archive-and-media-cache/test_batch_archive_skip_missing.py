"""批量归档的缺图跳过与逐篇隔离回归测试（spec 007 追加）。

背景（2026-10-06 线上事故）：用户 195 篇已完成笔记点「打包下载」卡住。
两个独立根因：

1. 端点写死 `if len(task_ids) > 100: return R.error(...)`，195 篇直接整批 400。
2. 一篇笔记引用了已被清理的截图时，`write_note_archive` 抛
   `NoteArchiveError`，路由放弃**整批** —— 195 篇里有 64 篇这样，于是
   即使放开上限也必然失败。

这里锁住修复后的行为：单篇严格模式不变（007 原有契约），批量模式跳过缺图
并继续收其余篇。
"""

import zipfile

import pytest

from app.utils.note_archive import NoteArchiveError, write_note_archive


def test_skip_missing_collects_skipped_assets_and_keeps_archive(tmp_path):
    """skip_missing=True：缺图记入 skipped，其余图正常入包，不抛错。"""
    root = tmp_path / "screenshots"
    root.mkdir()
    (root / "present.jpg").write_bytes(b"jpeg-data")
    archive_path = tmp_path / "note.zip"
    markdown = "![ok](/static/screenshots/present.jpg)\n![gone](/static/screenshots/gone.jpg)"

    skipped: list[str] = []
    count, size = write_note_archive(
        markdown, root, archive_path, skip_missing=True, skipped=skipped
    )

    # 只收进存在的那张
    assert (count, size) == (1, len(b"jpeg-data"))
    assert skipped == ["gone.jpg"]
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {"note.md", "assets/present.jpg"}


def test_skip_missing_does_not_change_other_failure_modes(tmp_path):
    """跳过缺图**不**放松路径穿越校验 —— 安全边界不受影响。"""
    root = tmp_path / "screenshots"
    root.mkdir()
    (tmp_path / "secret.jpg").write_bytes(b"secret")
    skipped: list[str] = []
    with pytest.raises(NoteArchiveError, match="超出截图目录"):
        write_note_archive(
            "![x](/static/screenshots/../secret.jpg)",
            root,
            tmp_path / "x.zip",
            skip_missing=True,
            skipped=skipped,
        )


def test_stored_compression_skips_inner_deflate(tmp_path):
    """压缩方式可注入：批量归档用 ZIP_STORED，避免「先压内层再压外层」的双重压缩。"""
    root = tmp_path / "screenshots"
    root.mkdir()
    (root / "a.jpg").write_bytes(b"x" * 4096)
    archive_path = tmp_path / "note.zip"

    skipped: list[str] = []
    write_note_archive(
        "![a](/static/screenshots/a.jpg)",
        root,
        archive_path,
        skip_missing=True,
        skipped=skipped,
        compression=zipfile.ZIP_STORED,
    )

    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
