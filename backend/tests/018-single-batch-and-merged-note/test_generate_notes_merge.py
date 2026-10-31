"""spec 018：/generate_notes 的合并分支（不建组、只入队一条任务）。

为什么要真库：合并分支的关键约束是「任务行只有一条」「绝不建组」，
这两件事只有跑真实 DAO 才看得见 —— 全部 patch 掉的话，测的是 mock 的返回值。
"""

import json
from unittest import mock

import app.db.models.note_groups
import app.db.models.video_tasks  # noqa: F401
import pytest
from app.db import engine as engine_module
from app.db.models.general_settings import GeneralSettings
from app.db.models.video_tasks import VideoTask
from app.enmus.note_enums import DownloadQuality
from app.routers import note as note_module
from app.routers.note import BatchGenerateRequest, generate_notes
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """临时 SQLite + 临时结果目录（绝不碰用户的 bili_note.db / note_results）。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'merge-submit-test.db'}",
        connect_args={"check_same_thread": False},
    )
    engine_module.Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)

    with factory() as db:
        db.add(GeneralSettings(id=1, active_provider_id=7, active_model_name="m"))
        db.commit()

    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    return factory


def _body(resp):
    return json.loads(resp.body)


def _ready():
    return mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value={"ready": True},
    )


def _item(bvid, p=1, title=None):
    item = {"bvid": bvid, "p": p, "video_id": f"{bvid}_p{p}" if p > 1 else bvid}
    if title:
        item["title"] = title
    return item


def _payload(items, **kwargs):
    return BatchGenerateRequest(
        platform="bilibili",
        items=items,
        quality=DownloadQuality.fast,
        model_name="m",
        provider_id="p",
        **kwargs,
    )


def _run(payload, create_group=None, in_flight=False, already_generated=False):
    dispatched = []
    create_group = create_group or mock.Mock(return_value={"id": "gid-1", "name": "组"})
    with (
        _ready(),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=in_flight),
        mock.patch.object(
            note_module, "_is_generated_task", return_value=already_generated
        ),
        mock.patch.object(
            note_module,
            "_dispatch_note_task",
            side_effect=lambda kw: dispatched.append(kw),
        ),
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
        mock.patch("app.db.note_group_dao.create_group", create_group),
    ):
        resp = generate_notes(payload, BackgroundTasks())
    return _body(resp), dispatched, create_group


def _rows(factory):
    session = factory()
    try:
        return session.query(VideoTask).all()
    finally:
        session.close()


def test_merge_creates_one_task_and_no_group(db_env):
    """决策 3：勾了合并就**不建组**，只产生一条任务。"""
    body, dispatched, create_group = _run(
        _payload(
            [_item("BV1a", 1, "第一集"), _item("BV1a", 2, "第二集")],
            merge=True,
            merge_title="我的合集",
        )
    )

    assert body["code"] == 0, body
    data = body["data"]
    assert data["merged"] is True
    assert data["group_id"] is None
    assert len(data["results"]) == 1
    assert create_group.call_count == 0

    rows = _rows(db_env)
    assert len(rows) == 1
    assert rows[0].video_id.startswith("merged_")
    assert rows[0].group_id is None

    assert len(dispatched) == 1
    kwargs = dispatched[0]
    assert kwargs["merge_title"] == "我的合集"
    assert kwargs["merge_polish"] is False
    assert [item["title"] for item in kwargs["merge_items"]] == ["第一集", "第二集"]


def test_merge_ignores_group_name(db_env):
    """合并时即使前端带了 group_name，也不能建组（组名只当标题兜底）。"""
    body, dispatched, create_group = _run(
        _payload([_item("BV1a")], merge=True, group_name="被忽略的组名")
    )

    assert body["code"] == 0, body
    assert create_group.call_count == 0
    assert dispatched[0]["merge_title"] == "被忽略的组名"


def test_merge_rejects_empty_items(db_env):
    body, dispatched, create_group = _run(_payload([], merge=True))
    assert body["code"] == 400
    assert dispatched == []
    assert _rows(db_env) == []


def test_merge_rejects_in_flight_items(db_env):
    body, dispatched, _ = _run(_payload([_item("BV1a")], merge=True), in_flight=True)
    assert body["code"] == 300103
    assert body["data"]["reason"] == "task_in_progress"
    assert dispatched == []
    assert _rows(db_env) == []


def test_non_merge_batch_still_creates_a_group(db_env):
    """回归：不勾合并时仍是「一次批量 = 一个组 + 每条任务一行」。"""
    body, dispatched, create_group = _run(
        _payload([_item("BV1a"), _item("BV1b")], group_name="普通批量")
    )

    assert body["code"] == 0, body
    assert create_group.call_count == 1
    assert body["data"]["group_id"] == "gid-1"
    assert len(dispatched) == 2
    assert len(_rows(db_env)) == 2
    # 普通批量的载荷里 merge_items 是 None（键在、值空），不会被当成合并任务。
    assert dispatched[0]["merge_items"] is None
