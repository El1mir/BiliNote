"""spec 009 ticket 01：批量分组里 001 尚未覆盖的空白。

``backend/tests/001-bilibili-batch-import/test_batch_generate_api.py`` 已经把
「一批只建 1 组」「空组名不建组」「整批跳过不建空组」「建组失败 300105」这些
用 mock 打过了。这个文件补的是**必须用真实 DAO + 真实临时库**才测得出的部分：

* 连续两次批量必须拿到**两个不同的组**（mock 永远返回 gid-1，测不出来）；
* 组名超长 / 组数达上限这类**由 DAO 内部规则拒绝**的场景，报错必须显式，
  且**一条任务都不能落进「未分组」** —— 静默退化正是 spec 009 决策 4 要消灭的；
* 单条 ``/generate_note`` 仍走未分组（决策 5），且绝不建组。

所以这里**不 patch** ``app.db.note_group_dao.create_group``，而是照
``test_note_group_api.py`` 的 ``api_env`` 手法把 ``SessionLocal`` 钉在临时库上，
让整条链路（路由 → DAO → SQLite）真跑。**绝不碰用户真实的 bili_note.db**。

关于响应码：``ResponseWrapper.error`` 返回 ``JSONResponse`` 且没传 ``status_code``，
业务错误在 HTTP 层仍是 200，错误码在 body 的 ``code`` 里 —— 断言一律看 ``code``。
"""

import json
from unittest import mock

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import engine as engine_module
from app.db import note_group_dao
from app.db.models.video_tasks import VideoTask
from app.db.models.general_settings import GeneralSettings
from app.db.note_group_dao import list_groups
from app.enmus.note_enums import DownloadQuality
from app.routers import note as note_module
from app.routers.note import (
    BatchGenerateRequest,
    VideoRequest,
    generate_note,
    generate_notes,
)

# 建表前必须先 import 这两个模型模块，否则它们的表不在 Base.metadata 里。
import app.db.models.note_groups  # noqa: F401
import app.db.models.video_tasks  # noqa: F401


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    """临时 SQLite + 临时结果目录；DAO 的 ``next(get_db())`` 每次都重读 SessionLocal。

    ``NOTE_OUTPUT_DIR`` 是 note.py 的模块级常量，必须 patch —— 否则任何写盘路径
    都会落到仓库里的 note_results/（用户真实数据）。
    """
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'batch-grouping-test.db'}",
        connect_args={"check_same_thread": False},
    )
    engine_module.Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)

    # Every task now requires a persisted global model selection before enqueue.
    with factory() as db:
        db.add(GeneralSettings(id=1, active_provider_id=7, active_model_name="m"))
        db.commit()

    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))

    # 闸门是模块级单例，跨用例泄漏；这里显式复位，避免别的用例把 limit 留在奇怪的值上。
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    return factory


def _body(resp):
    return json.loads(resp.body)


def _ready():
    """跳过「转写模型是否就绪」门禁（它要读真实转写配置）。"""
    return mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value={"ready": True},
    )


def _payload(items, group_name=None):
    return BatchGenerateRequest(
        platform="bilibili",
        items=items,
        quality=DownloadQuality.fast,
        model_name="m",
        provider_id="p",
        group_name=group_name,
    )


def _item(bvid):
    return {"bvid": bvid, "p": 1, "video_id": bvid}


def _dispatch_through(items, group_name=None):
    """跑一次 generate_notes，把分发拦下来收集 kwargs（不真起线程）。"""
    dispatched = []
    with (
        _ready(),
        mock.patch.object(note_module, "_is_generated_task", return_value=False),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=False),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(
            note_module,
            "_dispatch_note_task",
            side_effect=lambda kw: dispatched.append(kw),
        ),
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
    ):
        resp = generate_notes(_payload(items, group_name), BackgroundTasks())
    return _body(resp), dispatched


def _task_rows(factory):
    session = factory()
    try:
        return session.query(VideoTask).all()
    finally:
        session.close()


def test_two_consecutive_batches_create_two_distinct_groups(db_env):
    """spec §6 第一条验收：连跑两次批量 → 两个不同的组，成员各自正确。

    这条只能用真实 ``create_group``（uuid 主键）才测得出：001 的用例把
    ``create_group`` patch 成恒定 gid-1，两次提交会「看起来一样」。
    """
    first = [_item("BV1a"), _item("BV1b")]
    second = [_item("BV1c"), _item("BV1d")]

    body_a, dispatched_a = _dispatch_through(first, "合集甲")
    body_b, dispatched_b = _dispatch_through(second, "合集乙")

    assert body_a["code"] == 0
    assert body_b["code"] == 0

    gid_a = body_a["data"]["group_id"]
    gid_b = body_b["data"]["group_id"]
    assert gid_a and gid_b, "两次批量都应返回非空 group_id"
    assert gid_a != gid_b, "两次批量必须是两个不同的组"

    # 各自的成员必须全部带上**自己那一次**的 group_id（不能串台）。
    assert [kw["group_id"] for kw in dispatched_a] == [gid_a, gid_a]
    assert [kw["group_id"] for kw in dispatched_b] == [gid_b, gid_b]

    # 库里真的落了两个组，且每组各 2 条任务（_enqueue_task 走的是真实 DAO）。
    groups = {g["name"]: g for g in list_groups()}
    assert set(groups) == {"合集甲", "合集乙"}
    assert groups["合集甲"]["id"] == gid_a
    assert groups["合集乙"]["id"] == gid_b
    assert groups["合集甲"]["task_count"] == 2
    assert groups["合集乙"]["task_count"] == 2

    # 入队参数与库内归属对得上：4 条任务行，group_id 两两对应。
    rows = _task_rows(db_env)
    assert len(rows) == 4
    assert sorted(r.group_id for r in rows) == sorted([gid_a, gid_a, gid_b, gid_b])


def test_overlong_group_name_fails_loudly_and_enqueues_nothing(db_env):
    """组名 > 64 字符：必须报错，而不是静默落未分组（决策 4）。

    ``create_group`` → ``_clean_name`` 抛 ``NoteGroupError``，路由层转 300105。
    关键是**一条任务都不能入队** —— 否则用户会得到「报错了但任务其实在跑」。
    """
    long_name = "长" * (note_group_dao.MAX_GROUP_NAME_LENGTH + 1)
    enqueued = []
    with (
        _ready(),
        mock.patch.object(note_module, "_is_generated_task", return_value=False),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=False),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(
            note_module, "_enqueue_task", side_effect=lambda *a, **k: enqueued.append(a)
        ),
        mock.patch.object(note_module, "_dispatch_note_task") as dispatch,
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
    ):
        resp = generate_notes(_payload([_item("BV1a")], long_name), BackgroundTasks())

    body = _body(resp)
    assert body["code"] == 300105
    assert body["data"]["reason"] == "group_create_failed"
    assert enqueued == [], "建组失败时绝不能有任务被入队"
    assert dispatch.call_count == 0
    assert list_groups() == []


def test_group_limit_reports_error_and_never_falls_back_to_ungrouped(
    db_env, monkeypatch
):
    """组数达上限 → 明确报错，且**没有任何任务落进未分组**（spec §6 最后一条）。

    把 ``MAX_GROUPS`` 压成 1：先建满，再批量提交。``create_group`` 内部读的是
    模块全局 ``MAX_GROUPS``，所以 monkeypatch 该属性即可。
    """
    monkeypatch.setattr(note_group_dao, "MAX_GROUPS", 1)
    note_group_dao.create_group("已经满了的组")
    assert len(list_groups()) == 1

    enqueued = []
    with (
        _ready(),
        mock.patch.object(note_module, "_is_generated_task", return_value=False),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=False),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(
            note_module, "_enqueue_task", side_effect=lambda *a, **k: enqueued.append(a)
        ),
        mock.patch.object(note_module, "_dispatch_note_task") as dispatch,
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
    ):
        resp = generate_notes(
            _payload([_item("BV1a"), _item("BV1b")], "撞上限的组"), BackgroundTasks()
        )

    body = _body(resp)
    assert body["code"] == 300105
    assert body["data"]["reason"] == "group_create_failed"
    assert enqueued == []
    assert dispatch.call_count == 0
    # 库里仍然只有那 1 个组，**没有任何任务**（尤其不能有 group_id IS NULL 的孤儿）。
    assert len(list_groups()) == 1
    assert _task_rows(db_env) == []


def test_group_creation_is_deferred_when_nothing_is_pending(db_env):
    """整批命中「已在途」→ 根本不建组，响应 group_id 为 None（决策 5）。

    直接盯着两个可能的建组入口计数：``_resolve_batch_group``（路由层）与
    ``create_group``（DAO 层）。只要有一个被调到就说明「延后建组」失效了。
    """
    with (
        _ready(),
        mock.patch.object(note_module, "_is_generated_task", return_value=False),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=True),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(note_module, "_enqueue_task") as enqueue,
        mock.patch.object(note_module, "_dispatch_note_task") as dispatch,
        mock.patch.object(note_module, "_resolve_batch_group") as resolve,
        mock.patch.object(note_group_dao, "create_group") as create,
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
    ):
        resp = generate_notes(
            _payload([_item("BV1a"), _item("BV1b")], "不该被建的组"), BackgroundTasks()
        )

    body = _body(resp)
    assert body["code"] == 0
    assert body["data"]["group_id"] is None
    assert all(r["status"] == "skipped" for r in body["data"]["results"])
    assert resolve.call_count == 0, "整批无 pending 时不应触碰建组逻辑"
    assert create.call_count == 0
    assert enqueue.call_count == 0
    assert dispatch.call_count == 0
    assert list_groups() == []


def test_single_generate_note_stays_ungrouped(db_env):
    """spec 009 决策 5：单条入口行为不变 —— 落未分组，且绝不建组。"""
    request = VideoRequest(
        video_url="https://www.bilibili.com/video/BV1xx411c7mD",
        platform="bilibili",
        quality=DownloadQuality.fast,
        model_name="m",
        provider_id="p",
    )
    bg = BackgroundTasks()
    with (
        _ready(),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=False),
        mock.patch.object(note_module, "_check_disk_space", return_value=None),
        mock.patch.object(note_module, "_enqueue_task") as enqueue,
        mock.patch.object(note_group_dao, "create_group") as create,
        mock.patch.object(note_module, "NoteGenerator", return_value=mock.Mock()),
    ):
        resp = generate_note(request, bg)

    body = _body(resp)
    assert body["code"] == 0
    assert enqueue.call_count == 1
    # _enqueue_task(task_id, video_id, platform, group_id, payload) —— 第 4 个位置参数
    assert enqueue.call_args.args[3] is None
    assert create.call_count == 0
    assert list_groups() == []
    # 单条仍走 BackgroundTasks（批量才改走分发池）。
    assert len(bg.tasks) == 1
