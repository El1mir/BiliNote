"""spec 022 W2：数据根只拼一次 + 媒体资源能登记成相对路径。

R3 的成因：get_data_dir() 先取 <backend>/data 再 join("data")，返回
<backend>/data/data，而下载落盘在 <backend>/data（DATA_DIR 默认 "data"）。
media_resource_service._roots() 用前者做根，_managed_relative() 判越界，
于是每条任务的媒体登记都失败，日志刷「无法登记任务媒体资源」。

这里的用例对应验收第 4 条的前半段：临时 DATA_DIR 下登记成功、path 是相对路径。
"""

import os
from pathlib import Path

import pytest

from app.utils import path_helper
from app.services import media_resource_service


def _backend_root() -> Path:
    # app/utils/path_helper.py → parents[0]=utils, [1]=app, [2]=backend
    return Path(path_helper.__file__).resolve().parents[2]


def test_default_root_is_backend_data_not_double_nested(monkeypatch):
    monkeypatch.delenv("DATA_DIR", raising=False)
    root = Path(path_helper.get_data_dir()).resolve()
    assert root == (_backend_root() / "data").resolve()
    assert not str(root).replace("\\", "/").endswith("/data/data"), (
        "R3 回归：数据根又被拼成了 data/data"
    )


def test_absolute_data_dir_is_used_as_is(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert Path(path_helper.get_data_dir()).resolve() == tmp_path.resolve()


def test_relative_data_dir_resolves_against_backend(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "custom-data-022")
    expected = _backend_root() / "custom-data-022"
    try:
        assert Path(path_helper.get_data_dir()).resolve() == expected.resolve()
    finally:
        # 只清这个用例自己造的目录，别碰既有 data/
        if expected.is_dir() and not any(expected.iterdir()):
            expected.rmdir()


class _FakeQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


class _FakeDb:
    def __init__(self):
        self.added = []

    def query(self, *args, **kwargs):
        return _FakeQuery()

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass


def test_register_resource_uses_the_same_root_and_stores_relative_path(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    media_dir = tmp_path / "video" / "sub"
    media_dir.mkdir(parents=True)
    media_file = media_dir / "x.mp4"
    media_file.write_bytes(b"fake")

    fake_db = _FakeDb()

    class _Ctx:
        def __enter__(self):
            return fake_db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(media_resource_service, "SessionLocal", lambda: _Ctx())
    monkeypatch.setattr(
        media_resource_service,
        "get_retention_settings",
        lambda: {"screenshot_retention_days": 7, "media_retention_days": 3},
    )

    media_resource_service.register_resource("video", media_file, task_id="t-022")

    assert len(fake_db.added) == 1, "R3 回归：登记没有走到 add（多半又是越界异常）"
    row = fake_db.added[0]
    assert row.path == "video:video/sub/x.mp4", f"必须存相对路径，实际 {row.path}"
    assert row.size_bytes == 4
