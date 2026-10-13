"""spec 010：任务彻底删除、进行中守卫、批量删除、删除分组时连笔记一起删。

「删除」在这个项目里有两个容易出错的地方，这里都钉死：

1. **什么算删干净** —— DB 行 + 5 类派生文件。漏一个，任务就会在列表里阴魂不散
   （老的 ``/delete_task`` 空壳就是这么被发现的）。
2. **什么不能删** —— 进行中的任务。删掉它之后 DB 行和 ``.status.json`` 都没了，工作
   线程却还在跑，最后写出一个谁也看不见的孤儿结果，还继续占着下载与转写资源。

约定：不引入 conftest.py；业务错误码仍是 HTTP 200 + body ``code`` 非 0。
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import note_group_dao
from app.routers import note as note_module
from app.routers import note_group as group_module
from app.services import task_cleanup


@pytest.fixture(autouse=True)
def _clean_running_registry():
    """进程级登记表不能跨用例泄漏 —— 否则一个用例的「进行中」会把另一个用例锁死。"""
    task_cleanup.clear_running_tasks()
    yield
    task_cleanup.clear_running_tasks()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时结果目录 + 假 DB 删除。绝不碰用户真实的 ``bili_note.db``。"""
    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    # task_cleanup._output_dir() 延迟 import 路由模块再读这个常量，所以这里能生效。
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    app.include_router(group_module.router, prefix="/api")
    return TestClient(app), results_dir


def _status_file(results_dir, task_id, status):
    (results_dir / f"{task_id}.status.json").write_text(
        json.dumps({"status": status}), encoding="utf-8"
    )


def _ok(response):
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


# --------------------------------------------------------------- 单条删除语义


def test_delete_removes_row_and_all_artifact_files(env):
    client, results_dir = env
    for suffix in task_cleanup.TASK_ARTIFACT_SUFFIXES:
        (results_dir / f"t1{suffix}").write_text("{}", encoding="utf-8")
    # 不在后缀白名单里的文件：宁可留一个残骸，也不误删别的东西。
    (results_dir / "t1_extra.bin").write_text("keep", encoding="utf-8")

    data = _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))
    assert data["removed"] == 1
    assert set(data["files"]) == {f"t1{s}" for s in task_cleanup.TASK_ARTIFACT_SUFFIXES}
    for suffix in task_cleanup.TASK_ARTIFACT_SUFFIXES:
        assert not (results_dir / f"t1{suffix}").exists()
    assert (results_dir / "t1_extra.bin").exists()


def test_delete_does_not_touch_other_tasks_files(env):
    """前缀相同的兄弟任务不能被误伤（``t1`` vs ``t10``）。"""
    client, results_dir = env
    _status_file(results_dir, "t10", "SUCCESS")
    _status_file(results_dir, "t1", "SUCCESS")

    _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))
    assert not (results_dir / "t1.status.json").exists()
    assert (results_dir / "t10.status.json").exists()


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED"])
def test_finished_task_is_deletable(env, status):
    """终态都可删。FAILED 也是「已完成」—— 用户得能清掉失败任务。"""
    client, results_dir = env
    _status_file(results_dir, "t1", status)
    assert _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))["removed"] == 1


def test_status_file_marks_task_in_flight(env):
    client, results_dir = env
    _status_file(results_dir, "t1", "TRANSCRIBING")

    body = client.post("/api/delete_task_record", json={"task_id": "t1"}).json()
    assert body["code"] == note_module.CODE_TASK_IN_FLIGHT
    assert "仍在执行" in body["msg"]
    assert (results_dir / "t1.status.json").exists()


def test_queued_task_without_status_file_is_still_refused(env):
    """200 条批量里绝大多数卡在「已进池、还没轮到」—— 此时根本没有状态文件。

    这正是运行登记表存在的理由：只看状态文件会放行它们，而池子里的工作线程照样会
    把它们跑完，最后写出一堆谁也看不见的孤儿结果。
    """
    client, results_dir = env
    task_cleanup.mark_task_running("t1")
    assert not (results_dir / "t1.status.json").exists()

    body = client.post("/api/delete_task_record", json={"task_id": "t1"}).json()
    assert body["code"] == note_module.CODE_TASK_IN_FLIGHT

    # 注销之后就能删了 —— 守卫不能变成死锁。
    task_cleanup.unmark_task_running("t1")
    assert _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))["removed"] == 1


def test_corrupt_status_file_does_not_block_deletion(env):
    """状态文件损坏 → 读不出状态 → 按可删处理。不能因为一个坏文件把任务锁死。"""
    client, results_dir = env
    (results_dir / "t1.status.json").write_text("{not json", encoding="utf-8")
    assert _ok(client.post("/api/delete_task_record", json={"task_id": "t1"}))["removed"] == 1


@pytest.mark.parametrize("bad", ["", "   ", "../etc/passwd", "a/b", "x" * 129])
def test_invalid_task_id_is_rejected(env, bad):
    """task_id 会直接拼进文件名 —— 路径分隔符与超长串必须挡在路由层。"""
    client, _results_dir = env
    body = client.post("/api/delete_task_record", json={"task_id": bad}).json()
    assert body["code"] == 400


# ------------------------------------------------------------------- 批量删除


def test_batch_delete_is_isolated_per_item(env):
    """一条卡住不能拖垮整批 —— 批量接口最怕「重试一次还是全挂」。"""
    client, results_dir = env
    _status_file(results_dir, "busy", "TRANSCRIBING")
    _status_file(results_dir, "ok", "SUCCESS")

    data = _ok(client.post("/api/delete_task_records", json={"task_ids": ["busy", "ok"]}))
    # deleted 是 task_id 列表（后端已展平），failed 才是带原因的字典列表。
    assert data["deleted"] == ["ok"]
    assert [item["task_id"] for item in data["failed"]] == ["busy"]
    assert data["removed_rows"] == 1
    assert data["files"] == ["ok.status.json"]
    assert "仍在执行" in data["failed"][0]["error"]
    assert not (results_dir / "ok.status.json").exists()
    assert (results_dir / "busy.status.json").exists()


def test_batch_delete_dedups_and_keeps_order(env):
    client, results_dir = env
    for task_id in ("a", "b"):
        _status_file(results_dir, task_id, "SUCCESS")

    data = _ok(client.post("/api/delete_task_records", json={"task_ids": ["b", "a", "b"]}))
    assert data["deleted"] == ["b", "a"]


def test_batch_delete_reports_invalid_ids_in_failed(env):
    client, _results_dir = env
    data = _ok(client.post("/api/delete_task_records", json={"task_ids": ["ok", "../x"]}))
    assert data["deleted"] == ["ok"]
    assert [item["task_id"] for item in data["failed"]] == ["../x"]


def test_batch_delete_rejects_empty_and_oversized(env):
    client, _results_dir = env
    assert client.post("/api/delete_task_records", json={"task_ids": []}).json()["code"] == 400
    too_many = [f"t{i}" for i in range(note_module.MAX_BATCH_DELETE + 1)]
    body = client.post("/api/delete_task_records", json={"task_ids": too_many}).json()
    assert body["code"] == 400


# --------------------------------------------------- 删除分组：只删组 / 连笔记删


class _GroupState:
    """内存版分组 DAO 的替身。"""

    def __init__(self):
        self.members = {"g1": ["t1", "busy"]}
        # 真实实现里 delete_group 返回「退回未分组」的条数。删了行的任务不会再退回，
        # 所以由用例显式指定，不假装替身能算出来。
        self.affected = 0
        self.unbound = []


@pytest.fixture
def group_env(env, monkeypatch):
    client, results_dir = env
    state = _GroupState()

    # list_task_ids_in_group 是路由函数**内部** import 的，必须 patch 源模块的属性。
    monkeypatch.setattr(
        note_group_dao, "list_task_ids_in_group", lambda gid: list(state.members.get(gid, []))
    )

    def fake_delete_group(group_id):
        state.unbound.append(group_id)
        return state.affected

    monkeypatch.setattr(group_module, "delete_group", fake_delete_group)
    return client, results_dir, state


def test_group_delete_default_keeps_notes(group_env):
    """默认模式：一条笔记都不删（用户要的「单独删除组」）。"""
    client, results_dir, state = group_env
    state.affected = 2
    for task_id in ("t1", "busy"):
        _status_file(results_dir, task_id, "SUCCESS")

    data = _ok(client.post("/api/note_group/delete", json={"group_id": "g1"}))
    assert data == {"affected": 2, "deleted_tasks": [], "skipped_tasks": []}
    assert state.unbound == ["g1"]
    assert (results_dir / "t1.status.json").exists()
    assert (results_dir / "busy.status.json").exists()


def test_group_delete_with_tasks_removes_notes(group_env):
    """``delete_tasks=True``：组内终态笔记连文件一起删。"""
    client, results_dir, state = group_env
    state.affected = 1  # t1 的行被删了，只剩 busy 退回未分组
    _status_file(results_dir, "t1", "SUCCESS")
    _status_file(results_dir, "busy", "TRANSCRIBING")

    data = _ok(
        client.post("/api/note_group/delete", json={"group_id": "g1", "delete_tasks": True})
    )
    assert data["deleted_tasks"] == ["t1"]
    # 进行中的「busy」被跳过并退回未分组（用户决策 group_inflight）。
    assert [item["task_id"] for item in data["skipped_tasks"]] == ["busy"]
    assert "仍在执行" in data["skipped_tasks"][0]["reason"]
    assert data["affected"] == 1
    assert not (results_dir / "t1.status.json").exists()
    assert (results_dir / "busy.status.json").exists()


def test_group_delete_skips_registered_running_task_without_status_file(group_env):
    """排队中的任务没有状态文件，但登记在册 —— 同样必须跳过。"""
    client, _results_dir, state = group_env
    state.affected = 2
    task_cleanup.mark_task_running("t1")

    data = _ok(
        client.post("/api/note_group/delete", json={"group_id": "g1", "delete_tasks": True})
    )
    # t1 登记在册（排队中）→ 跳过；busy 既无状态文件也未登记 → 正常删除。
    assert data["deleted_tasks"] == ["busy"]
    assert [item["task_id"] for item in data["skipped_tasks"]] == ["t1"]


# --------------------------------------------------------------- 运行登记表本身


def test_guarded_runner_unmarks_after_success(monkeypatch):
    seen = []
    monkeypatch.setattr(note_module, "run_note_task", lambda **kw: seen.append(kw["task_id"]))

    note_module._run_note_task_guarded({"task_id": "t8"})
    assert seen == ["t8"]
    assert not task_cleanup.is_task_running("t8")


def test_guarded_runner_unmarks_even_on_failure(monkeypatch):
    """抛异常也必须注销，否则这条任务永远删不掉。"""

    def boom(**_kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(note_module, "run_note_task", boom)
    with pytest.raises(RuntimeError):
        note_module._run_note_task_guarded({"task_id": "t9"})
    assert not task_cleanup.is_task_running("t9")


def test_dispatch_registers_before_submit(monkeypatch):
    """入队**那一刻**就必须已登记：池子只有 8 个等待位，排在后面的会等很久。"""
    observed = []

    class FakePool:
        def submit(self, _fn, task_kwargs):
            observed.append(task_cleanup.is_task_running(task_kwargs["task_id"]))
            return None

    monkeypatch.setattr(note_module, "_get_dispatch_pool", lambda: FakePool())
    monkeypatch.setattr(note_module, "run_note_task", lambda **_kw: None)

    note_module._dispatch_note_task({"task_id": "t7"})
    assert observed == [True]


def test_dispatch_unmarks_when_submit_fails(monkeypatch):
    """提交失败（池已关闭）不能留下永久登记 —— 那会让任务永远删不掉。"""

    class DeadPool:
        def submit(self, _fn, _task_kwargs):
            raise RuntimeError("pool is shut down")

    monkeypatch.setattr(note_module, "_get_dispatch_pool", lambda: DeadPool())
    note_module._dispatch_note_task({"task_id": "t6"})
    assert not task_cleanup.is_task_running("t6")


def test_empty_task_id_is_never_registered():
    """空 id 不该进登记表，否则整个删除路径都会被一个空串卡住。"""
    task_cleanup.mark_task_running("")
    task_cleanup.mark_task_running(None)
    assert task_cleanup.running_task_ids() == frozenset()
    assert not task_cleanup.is_task_in_flight("")
