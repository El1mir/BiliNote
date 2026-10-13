"""spec 007：笔记分组接口 + 任务列表 + 删除任务记录的后端回归。

覆盖三个新接口：

* ``app/routers/note_group.py``（前缀 ``/note_group``，挂在 ``/api`` 下）
* ``GET  /api/task_list``（``app/routers/note.py``）
* ``POST /api/delete_task_record``（``app/routers/note.py``）

DB 隔离沿用 ``test_media_resources.py`` 的写法：临时 SQLite + ``create_all``，
再把 ``app.db.engine.SessionLocal`` 换成指向它的 sessionmaker。DAO 里的
``next(get_db())`` 每次都重新读 ``SessionLocal``，所以这一处替换就足以把整条
链路（路由 → DAO）钉在临时库上，**绝不会碰到用户真实的 ``bili_note.db``**
（那里面有 7 条用户在乎的任务记录）。

关于响应码：``ResponseWrapper.error`` 返回的是 ``JSONResponse`` 且没有传
``status_code``，所以业务错误在 HTTP 层仍然是 200，错误码在 body 的 ``code``
字段里。断言一律看 ``code``，不看 ``response.status_code``。
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import engine as engine_module
from app.db.note_group_dao import MAX_GROUPS, MAX_GROUP_NAME_LENGTH
from app.routers import note as note_module
from app.routers import note_group as note_group_module
from app.routers.note_group import UNGROUPED_ID

# 建表前必须先 import 这两个模型模块，否则它们的表不在 Base.metadata 里。
import app.db.models.note_groups  # noqa: F401
import app.db.models.video_tasks  # noqa: F401


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """临时库 + 临时结果目录，并把两个路由装进一个干净 FastAPI 应用。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'note-group-test.db'}",
        connect_args={"check_same_thread": False},
    )
    engine_module.Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)

    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    # note.py 的所有结果文件路径都从模块级 NOTE_OUTPUT_DIR 拼出来，patch 它即可。
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))

    app = FastAPI()
    app.include_router(note_group_module.router, prefix="/api")
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app), factory, results_dir


def _ok(response):
    """取出成功响应的 data；顺带断言 code == 0。"""
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def _fail(response, code=400):
    """取出业务错误；``code`` 是 body 里的业务码，不是 HTTP 状态码。"""
    body = response.json()
    assert body["code"] == code, body
    return body["msg"]


def _new_group(client, name="数学"):
    return _ok(client.post("/api/note_group", json={"name": name}))["group"]


def _task_ids_in(client, group_id=None):
    params = {} if group_id is None else {"group_id": group_id}
    return _ok(client.get("/api/note_group/tasks", params=params))["task_ids"]


def _write_result(results_dir: Path, task_id: str, title="标题", markdown="# 正文"):
    (results_dir / f"{task_id}.json").write_text(
        json.dumps({"markdown": markdown, "audio_meta": {"title": title}}),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# 1. GET /note_group
# --------------------------------------------------------------------------


def test_list_groups_returns_empty_ungrouped_virtual_bucket(api_env):
    client, _, _ = api_env
    data = _ok(client.get("/api/note_group"))

    assert data["groups"] == []
    assert data["ungrouped_id"] == UNGROUPED_ID
    assert data["ungrouped_count"] == 0
    # spec 009 决策 7：上限由 200 提到 1000 —— 每批必建新组，200 太紧。
    assert data["max_groups"] == MAX_GROUPS == 1000
    assert data["max_name_length"] == MAX_GROUP_NAME_LENGTH == 64


def test_list_groups_reports_task_count_per_group(api_env):
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t1", group_id=group["id"])
    insert_video_task("BV2", "bilibili", "t2", group_id=group["id"])
    insert_video_task("BV3", "bilibili", "t3")  # 未分组

    data = _ok(client.get("/api/note_group"))

    assert len(data["groups"]) == 1
    assert data["groups"][0]["id"] == group["id"]
    assert data["groups"][0]["name"] == "数学"
    assert data["groups"][0]["task_count"] == 2
    assert data["ungrouped_count"] == 1


# --------------------------------------------------------------------------
# 2. POST /note_group（新建）
# --------------------------------------------------------------------------


def test_create_group_returns_id_and_appends_position(api_env):
    client, _, _ = api_env
    first = _new_group(client, "数学")
    second = _new_group(client, "物理")

    assert first["name"] == "数学"
    assert second["name"] == "物理"
    assert len(first["id"]) == 32  # uuid4().hex
    # position 只用于排序，新组排在最后
    assert second["position"] > first["position"]

    ids = [g["id"] for g in _ok(client.get("/api/note_group"))["groups"]]
    assert ids == [first["id"], second["id"]]


@pytest.mark.parametrize("bad_name", ["", "   ", "\t\n"])
def test_create_group_rejects_blank_name(api_env, bad_name):
    client, _, _ = api_env
    assert (
        _fail(client.post("/api/note_group", json={"name": bad_name}))
        == "分组名称不能为空"
    )
    assert _ok(client.get("/api/note_group"))["groups"] == []


def test_create_group_rejects_over_long_name(api_env):
    client, _, _ = api_env
    msg = _fail(
        client.post("/api/note_group", json={"name": "x" * (MAX_GROUP_NAME_LENGTH + 1)})
    )
    assert str(MAX_GROUP_NAME_LENGTH) in msg
    assert _ok(client.get("/api/note_group"))["groups"] == []


def test_create_group_accepts_exactly_max_length_name(api_env):
    client, _, _ = api_env
    name = "x" * MAX_GROUP_NAME_LENGTH
    assert _new_group(client, name)["name"] == name


def test_create_group_trims_surrounding_whitespace(api_env):
    client, _, _ = api_env
    assert _new_group(client, "  数学  ")["name"] == "数学"


def test_create_group_refuses_beyond_max_groups(api_env):
    client, factory, _ = api_env
    from app.db.models.note_groups import NoteGroup

    # 直接灌满 MAX_GROUPS 行，避免真的发 MAX_GROUPS 次请求。
    session = factory()
    try:
        session.add_all(
            NoteGroup(id=uuid.uuid4().hex, name=f"g{i}", position=i)
            for i in range(MAX_GROUPS)
        )
        session.commit()
    finally:
        session.close()

    msg = _fail(client.post("/api/note_group", json={"name": "再来一个"}))
    assert str(MAX_GROUPS) in msg
    # 仍然是恰好 MAX_GROUPS 个，没有偷偷多建一个
    assert len(_ok(client.get("/api/note_group"))["groups"]) == MAX_GROUPS


# --------------------------------------------------------------------------
# 3. POST /note_group/rename
# --------------------------------------------------------------------------


def test_rename_group(api_env):
    client, _, _ = api_env
    group = _new_group(client, "旧名")

    renamed = _ok(
        client.post(
            "/api/note_group/rename", json={"group_id": group["id"], "name": "新名"}
        )
    )["group"]

    assert renamed["id"] == group["id"]
    assert renamed["name"] == "新名"
    assert _ok(client.get("/api/note_group"))["groups"][0]["name"] == "新名"


def test_rename_rejects_unknown_group_and_keeps_others_intact(api_env):
    client, _, _ = api_env
    group = _new_group(client)

    msg = _fail(
        client.post("/api/note_group/rename", json={"group_id": "nope", "name": "新名"})
    )
    assert msg == "分组不存在"
    assert _ok(client.get("/api/note_group"))["groups"][0]["name"] == group["name"]


def test_rename_rejects_blank_name(api_env):
    client, _, _ = api_env
    group = _new_group(client, "原名")

    assert (
        _fail(
            client.post(
                "/api/note_group/rename", json={"group_id": group["id"], "name": "  "}
            )
        )
        == "分组名称不能为空"
    )
    assert _ok(client.get("/api/note_group"))["groups"][0]["name"] == "原名"


# --------------------------------------------------------------------------
# 4. POST /note_group/delete —— 核心不变量：删组不删任务（m04885）
# --------------------------------------------------------------------------


def test_delete_group_keeps_its_tasks_alive_in_ungrouped(api_env):
    """用户删掉一个分组时的预期是「这个分组没了」，不是「里面的笔记也没了」。

    组内任务必须退回未分组（``group_id IS NULL``），任务行本身一条都不能少。
    """
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task, list_video_tasks

    group = _new_group(client)
    # 先建好 3 条任务行，再整批挂进组里
    for index in range(1, 4):
        insert_video_task(f"BV{index}", "bilibili", f"t{index}", group_id=group["id"])

    assert sorted(_task_ids_in(client, group["id"])) == ["t1", "t2", "t3"]

    assert (
        _ok(client.post("/api/note_group/delete", json={"group_id": group["id"]}))[
            "affected"
        ]
        == 3
    )

    data = _ok(client.get("/api/note_group"))
    assert data["groups"] == []
    # 任务全都还在，而且都回到了未分组
    assert data["ungrouped_count"] == 3
    assert sorted(_task_ids_in(client)) == ["t1", "t2", "t3"]
    assert sorted(row["task_id"] for row in list_video_tasks()) == ["t1", "t2", "t3"]
    assert all(row["group_id"] is None for row in list_video_tasks())


def test_delete_group_only_unassigns_its_own_members(api_env):
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    keep = _new_group(client, "保留")
    drop = _new_group(client, "删除")
    insert_video_task("BV1", "bilibili", "t_keep", group_id=keep["id"])
    insert_video_task("BV2", "bilibili", "t_drop", group_id=drop["id"])

    assert (
        _ok(client.post("/api/note_group/delete", json={"group_id": drop["id"]}))[
            "affected"
        ]
        == 1
    )

    assert [g["id"] for g in _ok(client.get("/api/note_group"))["groups"]] == [
        keep["id"]
    ]
    assert _task_ids_in(client, keep["id"]) == ["t_keep"]
    assert _task_ids_in(client) == ["t_drop"]


def test_delete_unknown_group_is_rejected(api_env):
    client, _, _ = api_env
    assert (
        _fail(client.post("/api/note_group/delete", json={"group_id": "nope"}))
        == "分组不存在"
    )


# --------------------------------------------------------------------------
# 5. POST /note_group/assign —— ""/哨兵 都等于未分组
# --------------------------------------------------------------------------


def test_assign_moves_task_into_group(api_env):
    client, _, _ = api_env
    from app.db.note_group_dao import get_task_group
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t1")

    assert (
        _ok(
            client.post(
                "/api/note_group/assign",
                json={"task_id": "t1", "group_id": group["id"]},
            )
        )["group_id"]
        == group["id"]
    )
    assert get_task_group("t1") == group["id"]
    assert _task_ids_in(client, group["id"]) == ["t1"]


@pytest.mark.parametrize("sentinel", ["", UNGROUPED_ID, None])
def test_assign_empty_or_sentinel_means_ungrouped(api_env, sentinel):
    """``""``、``'__ungrouped__'``、``null`` 三者都必须落到 group_id IS NULL。

    否则任务会被挂到一个字面量叫 ``__ungrouped__`` 的「假组」上，前端再也找不到它。
    """
    client, _, _ = api_env
    from app.db.note_group_dao import get_task_group
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t1", group_id=group["id"])
    assert get_task_group("t1") == group["id"]

    body = _ok(
        client.post(
            "/api/note_group/assign", json={"task_id": "t1", "group_id": sentinel}
        )
    )
    assert body["group_id"] is None
    assert get_task_group("t1") is None
    assert _task_ids_in(client) == ["t1"]
    assert _task_ids_in(client, group["id"]) == []
    # 没有人趁机构造出一个叫 __ungrouped__ 的真组
    assert all(
        g["name"] != UNGROUPED_ID for g in _ok(client.get("/api/note_group"))["groups"]
    )


def test_assign_rejects_unknown_task_or_group(api_env):
    client, _, _ = api_env
    from app.db.note_group_dao import get_task_group
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t1")

    # 任务不存在 → 拒绝（即使给的是个真组 id，也不能凭空改出归属）
    assert (
        _fail(
            client.post(
                "/api/note_group/assign",
                json={"task_id": "ghost", "group_id": group["id"]},
            )
        )
        == "任务不存在"
    )
    # 分组不存在 → 拒绝，且任务不能被挂到幽灵组上
    assert (
        _fail(
            client.post(
                "/api/note_group/assign", json={"task_id": "t1", "group_id": "ghost"}
            )
        )
        == "分组不存在"
    )
    assert get_task_group("t1") is None


# --------------------------------------------------------------------------
# 6. POST /note_group/assign_batch
# --------------------------------------------------------------------------


def test_assign_batch_moves_many_tasks_and_reports_affected(api_env):
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    for index in range(1, 4):
        insert_video_task(f"BV{index}", "bilibili", f"t{index}")

    assert (
        _ok(
            client.post(
                "/api/note_group/assign_batch",
                json={"task_ids": ["t1", "t2", "t3"], "group_id": group["id"]},
            )
        )["affected"]
        == 3
    )
    assert sorted(_task_ids_in(client, group["id"])) == ["t1", "t2", "t3"]

    # 再整批拖回未分组
    assert (
        _ok(
            client.post(
                "/api/note_group/assign_batch",
                json={"task_ids": ["t1", "t2"], "group_id": ""},
            )
        )["affected"]
        == 2
    )
    assert _task_ids_in(client, group["id"]) == ["t3"]
    assert sorted(_task_ids_in(client)) == ["t1", "t2"]


def test_assign_batch_with_empty_list_changes_nothing(api_env):
    client, _, _ = api_env
    assert (
        _ok(
            client.post(
                "/api/note_group/assign_batch", json={"task_ids": [], "group_id": None}
            )
        )["affected"]
        == 0
    )


def test_assign_batch_rejects_unknown_group_without_touching_tasks(api_env):
    client, _, _ = api_env
    from app.db.note_group_dao import get_task_group
    from app.db.video_task_dao import insert_video_task

    insert_video_task("BV1", "bilibili", "t1")

    assert (
        _fail(
            client.post(
                "/api/note_group/assign_batch",
                json={"task_ids": ["t1"], "group_id": "ghost"},
            )
        )
        == "分组不存在"
    )
    assert get_task_group("t1") is None


# --------------------------------------------------------------------------
# 7. GET /note_group/tasks
# --------------------------------------------------------------------------


def test_list_group_tasks_defaults_to_ungrouped(api_env):
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t_in", group_id=group["id"])
    insert_video_task("BV2", "bilibili", "t_out")

    # 不传 group_id = 未分组
    data = _ok(client.get("/api/note_group/tasks"))
    assert data["task_ids"] == ["t_out"]
    assert data["total"] == 1

    # 传哨兵值同样 = 未分组
    assert _ok(client.get("/api/note_group/tasks", params={"group_id": UNGROUPED_ID}))[
        "task_ids"
    ] == ["t_out"]

    # 传真实组 id 才拿到组内的
    data = _ok(client.get("/api/note_group/tasks", params={"group_id": group["id"]}))
    assert data["task_ids"] == ["t_in"]
    assert data["total"] == 1


def test_list_group_tasks_for_unknown_group_is_empty(api_env):
    client, _, _ = api_env
    data = _ok(client.get("/api/note_group/tasks", params={"group_id": "ghost"}))
    assert data == {"task_ids": [], "total": 0}


# --------------------------------------------------------------------------
# 8. GET /api/task_list
# --------------------------------------------------------------------------


def test_task_list_is_empty_without_rows(api_env):
    client, _, _ = api_env
    assert _ok(client.get("/api/task_list")) == {"tasks": [], "total": 0}


def test_task_list_joins_group_and_reads_title_and_has_note(api_env):
    client, _, results_dir = api_env
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client, "数学")
    insert_video_task("BV1", "bilibili", "t_done", group_id=group["id"])
    insert_video_task("BV2", "bilibili", "t_no_note")
    insert_video_task("BV3", "bilibili", "t_no_file")

    _write_result(results_dir, "t_done", title="视频标题", markdown="# 正文")
    # markdown 是空串 / 只有空白 → has_note 必须为 False
    _write_result(results_dir, "t_no_note", title="没生成出来", markdown="   ")

    data = _ok(client.get("/api/task_list"))
    assert data["total"] == 3
    by_id = {task["task_id"]: task for task in data["tasks"]}
    assert set(by_id) == {"t_done", "t_no_note", "t_no_file"}

    done = by_id["t_done"]
    assert done["video_id"] == "BV1"
    assert done["platform"] == "bilibili"
    assert done["group_id"] == group["id"]
    assert done["group_name"] == "数学"  # 由 list_groups() 拼出来的显示名
    assert done["title"] == "视频标题"  # 来自 audio_meta.title
    assert done["has_note"] is True
    assert done["created_at"]  # 非空字符串

    blank = by_id["t_no_note"]
    assert blank["title"] == "没生成出来"
    assert blank["has_note"] is False  # markdown 全是空白 → 不算有笔记

    missing = by_id["t_no_file"]
    assert missing["title"] == ""  # 结果文件不存在 → 空标题
    assert missing["has_note"] is False
    assert missing["group_id"] is None
    assert missing["group_name"] == ""


def test_task_list_title_is_empty_when_result_json_is_broken(api_env):
    client, _, results_dir = api_env
    from app.db.video_task_dao import insert_video_task

    insert_video_task("BV1", "bilibili", "t_bad")
    (results_dir / "t_bad.json").write_text("{ this is not json", encoding="utf-8")

    task = _ok(client.get("/api/task_list"))["tasks"][0]
    assert task["title"] == ""
    assert task["has_note"] is False  # 解析失败不能抛 500


def test_task_list_group_name_is_empty_for_ungrouped(api_env):
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    _new_group(client, "别的组")
    insert_video_task("BV1", "bilibili", "t1")

    task = _ok(client.get("/api/task_list"))["tasks"][0]
    assert task["group_id"] is None
    assert task["group_name"] == ""


# --------------------------------------------------------------------------
# 9. POST /api/delete_task_record
# --------------------------------------------------------------------------


def test_delete_task_record_removes_row_and_derived_files(api_env):
    client, _, results_dir = api_env
    from app.db.video_task_dao import insert_video_task, list_video_tasks

    insert_video_task("BV1", "bilibili", "t1")
    _write_result(results_dir, "t1")
    (results_dir / "t1.status.json").write_text("{}", encoding="utf-8")
    (results_dir / "t1_transcript.json").write_text("{}", encoding="utf-8")

    data = _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))

    assert data["task_id"] == "t1"
    assert data["removed"] == 1
    assert sorted(data["files"]) == [
        "t1.json",
        "t1.status.json",
        "t1_transcript.json",
    ]
    # 行真的没了
    assert list_video_tasks() == []
    assert _ok(client.get("/api/task_list"))["total"] == 0
    # 文件真的被 unlink 了
    for name in data["files"]:
        assert not (results_dir / name).exists()


def test_delete_task_record_unlinks_only_that_tasks_files(api_env):
    client, _, results_dir = api_env
    from app.db.video_task_dao import insert_video_task

    insert_video_task("BV1", "bilibili", "t1")
    insert_video_task("BV2", "bilibili", "t2")
    _write_result(results_dir, "t1")
    _write_result(results_dir, "t2")

    _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))

    assert not (results_dir / "t1.json").exists()
    assert (results_dir / "t2.json").exists()  # 别人的文件必须还在
    assert [task["task_id"] for task in _ok(client.get("/api/task_list"))["tasks"]] == [
        "t2"
    ]


def test_delete_task_record_is_idempotent_for_missing_task(api_env):
    client, _, _ = api_env
    data = _ok(
        client.post("/api/delete_task_record", json={"task_id": "never_existed"})
    )
    assert data == {"task_id": "never_existed", "removed": 0, "files": []}


@pytest.mark.parametrize(
    "bad_task_id",
    [
        "../evil",  # 路径穿越
        "a b",  # 空格不在白名单里
        "",  # 空
        "   ",  # 纯空白（strip 后为空）
        "a/b",
        "a\\b",
        "t1.json",  # 点号不在白名单里
        "任务",  # 非 ASCII
        "x" * 129,  # 超过 128 位
    ],
)
def test_delete_task_record_rejects_invalid_task_id_and_deletes_nothing(
    api_env, bad_task_id
):
    """非法 task_id 一律 400，且不能删掉任何行/任何文件。"""
    client, _, results_dir = api_env
    from app.db.video_task_dao import insert_video_task, list_video_tasks

    insert_video_task("BV1", "bilibili", "t1")
    _write_result(results_dir, "t1")

    msg = _fail(client.post("/api/delete_task_record", json={"task_id": bad_task_id}))
    assert msg in {"缺少 task_id", "任务标识无效"}

    assert [row["task_id"] for row in list_video_tasks()] == ["t1"]
    assert (results_dir / "t1.json").exists()


def test_delete_task_record_does_not_escape_the_results_directory(api_env, tmp_path):
    """``../evil`` 这类值绝不能被拼成 ``note_results/../evil.json`` 去删外面的文件。"""
    client, _, results_dir = api_env
    outside = results_dir.parent / "evil.json"
    outside.write_text("{}", encoding="utf-8")

    assert (
        _fail(client.post("/api/delete_task_record", json={"task_id": "../evil"}))
        == "任务标识无效"
    )
    assert outside.exists()


def test_delete_task_record_clears_group_membership(api_env):
    """删掉任务后，它不该再出现在任何分组的成员列表里。"""
    client, _, _ = api_env
    from app.db.video_task_dao import insert_video_task

    group = _new_group(client)
    insert_video_task("BV1", "bilibili", "t1", group_id=group["id"])
    assert _task_ids_in(client, group["id"]) == ["t1"]

    _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))

    assert _task_ids_in(client, group["id"]) == []
    assert _task_ids_in(client) == []
    assert _ok(client.get("/api/note_group"))["groups"][0]["task_count"] == 0
