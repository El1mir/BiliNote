"""spec 014 ticket 03：失效挂载点 —— 每条删除/覆盖路径都必须让注册表失效。

为什么这个文件值得单独存在：注册表的键只有 ``task_id``、**没有指纹**（指纹机制在
二次审核里被推翻，见 spec §12.1）。于是「删除/覆盖之后还能读到旧值」是这套设计
唯一的高危失效模式，而且**完全不可自愈** —— 没有任何机制会在读的时候发现陈旧。

它长这样：

- 删除任务后前端刷新列表，那条任务**又冒出来**（`backend/app/routers/note.py:1994`
  附近的注释记录了同一症状）；
- 失败任务重试后，前端一直显示旧的 ``FAILED``（重试复用同一个 ``task_id`` 原地
  重跑，`backend/app/routers/note.py:2118` 决策 2）。

因此本文件既有「行为断言」（这几条路径现在确实失效了），也有「结构断言」
（失效挂在删除的**同一个函数**里，日后新增删除路径不会漏挂）。

口径提醒：``app/`` 下有 Cython 产物，``open`` 计数不可信，**``stat`` 计数才可信**
（见 conftest.py）。本文件不需要计数，只断言注册表与返回体。
"""

import json

from app.db import video_task_dao
from app.routers import note as note_module
from app.services import note as note_service
from app.services import task_cleanup, task_retry, task_status_cache

#: 终态任务在 ``.status.json`` 里的典型内容（216 字节量级）。
_TERMINAL_ON_DISK = {
    "status": "SUCCESS",
    "stage": "success",
    "stage_label": "已完成",
    "progress": 100,
    "stage_progress": 100,
    "message": "",
    "detail": {},
    "updated_at": "2026-10-14T12:00:00+00:00",
}


def _write_status(results_dir, task_id, payload=None):
    body = dict(_TERMINAL_ON_DISK) if payload is None else dict(payload)
    (results_dir / f"{task_id}.status.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8"
    )
    return body


def _read(task_id, **kwargs):
    """``_read_task_status`` 的包装：断言拿得到状态后再返回（顺便收窄类型）。"""
    kwargs.setdefault("include_result", False)
    payload = note_module._read_task_status(task_id, **kwargs)
    assert payload is not None, f"{task_id} 应当有状态"
    return payload


def _cached(task_id):
    payload = task_status_cache.get(task_id)
    assert payload is not None, f"注册表里没有 {task_id}"
    return payload


def _make_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app)


# --------------------------------------------------------------- 单条删除


def test_delete_drops_registry(results_dir, monkeypatch):
    """不变量 ①：删除后不返回旧值，而且**无法**从注册表再读到它。"""
    task_id = "t-del"
    _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)

    assert _read(task_id)["status"] == "SUCCESS"  # 预热：注册表里现在是 SUCCESS

    payload = task_cleanup.delete_task_completely(task_id)

    assert payload["removed"] == 1
    assert task_status_cache.get(task_id) is None, "删除没有让注册表失效——任务会「删了又冒出来」"
    assert note_module._read_task_status(task_id, unknown_is_none=True) is None


def test_delete_endpoint_drops_registry(results_dir, monkeypatch):
    """走 HTTP 的同一件事（端点与服务的接线也要覆盖）。"""
    task_id = "t-del-http"
    _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    assert _read(task_id)["status"] == "SUCCESS"

    body = _make_client().post("/api/delete_task_record", json={"task_id": task_id}).json()

    assert body["code"] == 0, body
    assert body["data"]["task_id"] == task_id
    assert task_status_cache.get(task_id) is None


def test_deleting_an_unknown_task_is_harmless(results_dir, monkeypatch):
    """删一个本来就不存在的 id：不抛、``removed=0``，也不该在注册表里留下什么。"""
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 0)

    payload = task_cleanup.delete_task_completely("t-ghost")

    assert payload["removed"] == 0
    assert task_status_cache.get("t-ghost") is None


# --------------------------------------------------------------- 批量删除


def test_batch_delete_drops_every_successful_id(results_dir, monkeypatch):
    """批量删除必须**逐条**失效——不是整表清空，也不能漏掉任何一条。"""
    task_ids = [f"t-batch-{index}" for index in range(3)]
    for task_id in task_ids:
        _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    for task_id in task_ids:
        _read(task_id)

    body = (
        _make_client()
        .post("/api/delete_task_records", json={"task_ids": task_ids})
        .json()
    )

    assert body["code"] == 0, body
    assert set(body["data"]["deleted"]) == set(task_ids)
    assert body["data"]["failed"] == []
    assert all(task_status_cache.get(task_id) is None for task_id in task_ids)


def test_batch_delete_isolates_failures(results_dir, monkeypatch):
    """部分成功部分失败是既有语义：成功的那几条必须已经失效，失败的那条不受影响。"""
    good = ["t-ok-0", "t-ok-1"]
    for task_id in good:
        _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    for task_id in good:
        _read(task_id)

    body = (
        _make_client()
        .post(
            "/api/delete_task_records",
            json={"task_ids": good + ["../etc/passwd"]},
        )
        .json()
    )

    data = body["data"]
    assert body["code"] == 0, body
    assert data["deleted"] == good
    assert [item["task_id"] for item in data["failed"]] == ["../etc/passwd"]
    assert all(task_status_cache.get(task_id) is None for task_id in good)
    # 非法 id 根本没进过注册表，也不该因为这次调用被清掉什么。
    assert task_status_cache.get("../etc/passwd") is None


def test_in_flight_delete_is_rejected_and_keeps_registry(results_dir, monkeypatch):
    """进行中守卫语义不变：拒绝删除，且**不能**顺手把注册表清掉。"""
    task_id = "t-busy"
    _write_status(results_dir, task_id)
    assert _read(task_id)["status"] == "SUCCESS"
    monkeypatch.setattr(task_cleanup, "is_task_in_flight", lambda _tid: True)

    body = _make_client().post("/api/delete_task_record", json={"task_id": task_id}).json()

    assert body["code"] == note_module.CODE_TASK_IN_FLIGHT, body
    assert _cached(task_id)["status"] == "SUCCESS"


# ----------------------------------------------------------------- 重试


def test_retry_overwrites_stale_failure(results_dir, monkeypatch):
    """不变量 ②：重试后立刻查询，看到的是**新状态**而不是注册表里的 FAILED。

    这是本 ticket 风险最高的一条：重试复用同一个 ``task_id`` 原地重跑，键里没有
    指纹，若写路径不入注册表，前端会一直显示上一次的 FAILED。
    """
    task_id = "t-retry"
    _write_status(
        results_dir,
        task_id,
        payload={**_TERMINAL_ON_DISK, "status": "FAILED", "message": "旧的失败原因"},
    )
    assert _read(task_id)["status"] == "FAILED"  # 预热：注册表里现在是 FAILED

    monkeypatch.setattr(
        video_task_dao, "list_recoverable_tasks", lambda: [{"task_id": task_id}]
    )
    monkeypatch.setattr(task_retry, "_select_retryable", lambda rows: (list(rows), []))
    monkeypatch.setattr(
        task_retry,
        "payload_from_row",
        lambda _row: {"video_url": "https://www.bilibili.com/video/BV1xx", "platform": "bilibili"},
    )
    dispatched = []
    monkeypatch.setattr(
        note_module, "_dispatch_note_task", lambda kwargs: dispatched.append(kwargs)
    )

    stats = task_retry.retry_failed_tasks()

    assert stats["requeued"] == [task_id]
    assert [item["task_id"] for item in dispatched] == [task_id]

    state = _cached(task_id)
    assert state["status"] == "PENDING", "重试后注册表里还是旧状态"
    assert state["message"] == "用户手动重试"

    # 投影文件也必须同步被覆盖（重启后读回的是新状态，不是旧的 FAILED）。
    assert task_retry.read_task_status(task_id) == "PENDING"


def test_retry_writes_the_new_state_before_requeueing(results_dir, monkeypatch):
    """顺序不变量：**先**写回 PENDING，**再**入队。

    反过来的话，重试刚入队的那一小段时间里注册表仍是 FAILED、磁盘上也仍是旧的
    FAILED 文件；任何一次轮询都会把旧状态再缓存一遍，用户看到「点了重试没反应」。
    """
    task_id = "t-retry-order"
    _write_status(
        results_dir,
        task_id,
        payload={**_TERMINAL_ON_DISK, "status": "FAILED", "message": "旧的失败原因"},
    )
    _read(task_id)

    monkeypatch.setattr(
        video_task_dao, "list_recoverable_tasks", lambda: [{"task_id": task_id}]
    )
    monkeypatch.setattr(task_retry, "_select_retryable", lambda rows: (list(rows), []))
    monkeypatch.setattr(
        task_retry,
        "payload_from_row",
        lambda _row: {"video_url": "https://www.bilibili.com/video/BV1xx", "platform": "bilibili"},
    )

    seen_at_dispatch = {}

    def fake_dispatch(kwargs):
        seen_at_dispatch["state"] = task_status_cache.get(kwargs["task_id"])
        raise RuntimeError("测试里不真的入队")

    monkeypatch.setattr(note_module, "_dispatch_note_task", fake_dispatch)

    stats = task_retry.retry_failed_tasks()

    # 入队失败会被如实记进 skipped，但状态必须在那一刻就已经是 PENDING。
    assert stats["requeued"] == []
    assert seen_at_dispatch["state"] is not None, "入队时注册表还是空的——顺序反了"
    assert seen_at_dispatch["state"]["status"] == "PENDING"


# --------------------------------------------------- 重启与结构性保障


def test_registry_restart_reads_back_from_the_projection_file(results_dir):
    """进程重启（注册表为空）后仍然读得回——本设计不做落盘缓存，投影文件是持久副本。"""
    task_id = "t-restart"
    note_service.NoteGenerator()._update_status(task_id, "TRANSCRIBING", message="进行中")
    assert _cached(task_id)["status"] == "TRANSCRIBING"

    task_status_cache.clear()  # 新进程：注册表是空的

    assert _read(task_id)["status"] == "TRANSCRIBING"
    assert _read(task_id)["message"] == "进行中"


def test_all_delete_paths_share_one_chokepoint(results_dir, monkeypatch):
    """结构保障：两个删除端点都走 ``delete_task_completely`` —— 失效挂在它里面。

    日后新增删除路径时，只要复用这个入口就自动获得失效；一旦有人另写一份删除
    逻辑（绕开这个函数），这个用例会失败，提示他去看 ``task_cleanup`` 里的失效代码。
    """
    calls = []
    real = task_cleanup.delete_task_completely

    def spy(task_id, **kwargs):
        calls.append(task_id)
        return real(task_id, **kwargs)

    monkeypatch.setattr(task_cleanup, "delete_task_completely", spy)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)

    client = _make_client()
    client.post("/api/delete_task_record", json={"task_id": "t-one"})
    client.post("/api/delete_task_records", json={"task_ids": ["t-two", "t-three"]})

    assert calls == ["t-one", "t-two", "t-three"]


def test_artifacts_are_removed_before_the_registry_is_dropped(results_dir, monkeypatch):
    """顺序不变量：先删投影文件、再删内存。

    反过来的话会开一个窗口——内存已清、磁盘上的 ``.status.json`` 还在，任何在这
    期间到达的轮询都会把**已删除**的任务状态从文件里读回来并重新缓存。
    """
    task_id = "t-order"
    _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    assert _read(task_id)["status"] == "SUCCESS"

    observed = {}
    real_delete_artifacts = task_cleanup._delete_artifacts
    real_drop = task_status_cache.drop

    def artifacts_spy(task_id_arg):
        observed["cached_at_delete_entry"] = task_status_cache.get(task_id_arg)
        observed["file_exists_at_delete_entry"] = (
            results_dir / f"{task_id_arg}.status.json"
        ).is_file()
        return real_delete_artifacts(task_id_arg)

    def drop_spy(task_id_arg):
        observed["file_exists_at_drop"] = (
            results_dir / f"{task_id_arg}.status.json"
        ).is_file()
        return real_drop(task_id_arg)

    monkeypatch.setattr(task_cleanup, "_delete_artifacts", artifacts_spy)
    monkeypatch.setattr(task_status_cache, "drop", drop_spy)

    task_cleanup.delete_task_completely(task_id)

    assert observed["file_exists_at_delete_entry"] is True, "探针没测到东西：删文件时文件已经没了"
    assert observed["cached_at_delete_entry"] is not None, "删文件之前内存就已经清了——顺序反了"
    assert observed["file_exists_at_drop"] is False, "清内存时投影文件还在——顺序反了"
    assert task_status_cache.get(task_id) is None
