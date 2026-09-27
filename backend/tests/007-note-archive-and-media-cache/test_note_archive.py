import zipfile

import pytest

from app.utils.note_archive import NoteArchiveError, write_note_archive


def test_archive_rewrites_local_assets_and_preserves_remote(tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    image = root / "shot 1.jpg"
    image.write_bytes(b"jpeg-data")
    archive_path = tmp_path / "note.zip"
    markdown = "![local](/static/screenshots/shot%201.jpg)\n![remote](https://example.com/x.png)"

    count, size = write_note_archive(markdown, root, archive_path)

    assert (count, size) == (1, len(b"jpeg-data"))
    with zipfile.ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {"note.md", "assets/shot_1.jpg"}
        note = archive.read("note.md").decode()
        assert "![local](assets/shot_1.jpg)" in note
        assert "![remote](https://example.com/x.png)" in note


def test_archive_rejects_path_traversal(tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    outside = tmp_path / "secret.jpg"
    outside.write_bytes(b"secret")
    with pytest.raises(NoteArchiveError, match="超出截图目录"):
        write_note_archive("![x](/static/screenshots/../secret.jpg)", root, tmp_path / "x.zip")


def test_archive_errors_on_missing_local_asset(tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    with pytest.raises(NoteArchiveError, match="图片不存在"):
        write_note_archive("![x](/static/screenshots/missing.jpg)", root, tmp_path / "x.zip")


def test_archive_enforces_asset_count_and_size_limits(tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    (root / "a.jpg").write_bytes(b"1234")
    with pytest.raises(NoteArchiveError, match="数量超过"):
        write_note_archive("![a](/static/screenshots/a.jpg)", root, tmp_path / "x.zip", max_files=0)
    with pytest.raises(NoteArchiveError, match="总大小超过"):
        write_note_archive("![a](/static/screenshots/a.jpg)", root, tmp_path / "x.zip", max_bytes=2)
