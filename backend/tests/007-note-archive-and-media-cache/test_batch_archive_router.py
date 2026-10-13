"""`POST /api/task_archives` 批量归档的边界与隔离回归（spec 007 追加）。

锁定 2026-10-06 事故的两条根因修复：批次上限超过原来的 100，且单篇损坏或
缺图不能让同批的其他笔记一起失败。数据库与文件目录全部隔离在临时路径中。
"""

import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import engine as engine_module
from app.routers import note as note_module

# 建表前先 import 模型模块，保证表在 Base.metadata 里。
import app.db.models.note_groups  # noqa: F401
import app.db.models.video_tasks  # noqa: F401


@pytest.fixture
def archive_env(tmp_path, monkeypatch):
    """临时库 + 临时笔记结果目录 + 临时截图目录，装出一个干净的应用。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'archive-test.db'}",
        connect_args={"check_same_thread": False},
    )
    engine_module.Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)

    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    shots_dir = tmp_path / "screenshots"
    shots_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))
    monkeypatch.setattr(note_module, "IMAGE_OUTPUT_DIR", shots_dir)

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app), results_dir, shots_dir


def _write_note(results_dir, task_id, markdown, title="笔记标题"):
    (results_dir / f"{task_id}.json").write_text(
        json.dumps({"markdown": markdown, "title": title}), encoding="utf-8"
    )


def test_batch_over_old_hundred_limit_is_archived(archive_env):
    """超过旧上限 100 的真实请求成功归档，避免只测配置常量。"""
    client, results_dir, _ = archive_env
    task_ids = [f"task-{index:03d}" for index in range(101)]
    for index, task_id in enumerate(task_ids):
        _write_note(results_dir, task_id, f"# 笔记 {index}\n正文", f"笔记-{index:03d}")

    response = client.post("/api/task_archives", json={"task_ids": task_ids})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-archive-notes"] == "101"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len([name for name in archive.namelist() if name.endswith("note.md")]) == 101


def test_missing_screenshots_do_not_sink_the_whole_batch(archive_env):
    """一篇笔记引用已被清理的截图，只跳过该图片，其余内容照常归档。"""
    client, results_dir, shots_dir = archive_env
    (shots_dir / "alive.jpg").write_bytes(b"jpeg")
    _write_note(results_dir, "task-good", "![ok](/static/screenshots/alive.jpg)", "好的那篇")
    _write_note(results_dir, "task-gone", "![x](/static/screenshots/vanished.jpg)", "缺图的那篇")

    response = client.post(
        "/api/task_archives", json={"task_ids": ["task-good", "task-gone"]}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-archive-notes"] == "2"
    assert response.headers["x-archive-skipped"] == "0"
    assert response.headers["x-archive-missing-assets"] == "1"


def test_corrupt_note_is_skipped_and_others_survive(archive_env):
    """结果文件损坏的那篇被跳过，并体现在 X-Archive-Skipped 里。"""
    client, results_dir, shots_dir = archive_env
    (shots_dir / "ok.jpg").write_bytes(b"jpeg")
    _write_note(results_dir, "task-healthy", "![a](/static/screenshots/ok.jpg)")
    (results_dir / "task-broken.json").write_text("{ 这不是合法 JSON", encoding="utf-8")

    response = client.post(
        "/api/task_archives", json={"task_ids": ["task-healthy", "task-broken"]}
    )

    assert response.status_code == 200
    assert response.headers["x-archive-notes"] == "1"
    assert response.headers["x-archive-skipped"] == "1"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert any(name.endswith("note.md") for name in archive.namelist())


def test_all_notes_missing_still_reports_an_error(archive_env):
    """整批没有任何可下载内容时，仍要给业务错误而不是空 zip。"""
    client, _, _ = archive_env
    response = client.post("/api/task_archives", json={"task_ids": ["not-on-disk"]})

    body = response.json()
    assert body["code"] == 400
    assert "没有找到可下载的已完成笔记" in body["msg"]


def test_empty_selection_is_rejected(archive_env):
    client, _, _ = archive_env
    body = client.post("/api/task_archives", json={"task_ids": []}).json()
    assert body["code"] == 400
