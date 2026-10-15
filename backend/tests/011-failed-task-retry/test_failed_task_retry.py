"""失败任务批量重试（spec 011）。

这个文件钉住四件事，每一件都对应一个会静默出错的地方：

1. **只有 FAILED 重试**。SUCCESS 重试会覆盖用户已看过的笔记；在途任务重试会让同一个
   ``task_id`` 被两个线程同时写。这两条如果错了，测试全绿而用户丢数据。
2. **原地重试**：task_id 不变、DB 行不新增。用户要的是「那条失败的再跑一遍」，不是
   「列表里多出一条」。
3. **参数沿用创建时的 payload_json**，而不是回落到默认值 —— 回落的表现是「重试出来的
   笔记参数不对」，很难被发现。
4. **如实汇报跳过项**：被跳过的任务必须带原因返回，静默跳过等于让用户以为全都重试了。

约定（与 009/010 一致）：不引入 conftest.py；断言读 body 的 ``code`` 字段（业务错误
仍是 HTTP 200）；``NOTE_OUTPUT_DIR`` 用 monkeypatch 指到 tmp_path。
"""

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.video_tasks import VideoTask
from app.routers import note as note_module
from app.services import note as note_service
from app.services import task_retry

TASK_OK = "ok-task"
TASK_FAILED = "failed-task"
TASK_BUSY = "busy-task"
TASK_SUCCESS = "success-task"


def _write_status(results_dir, task_id: str, status: str, message: str = "") -> None:
    payload = {"task_id": task_id, "status": status}
    if message:
        payload["message"] = message
    path = os.path.join(str(results_dir), f"{task_id}.status.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _write_payload(task_id: str, **overrides) -> str:
    """造一份 payload_json —— 形状与 `_build_task_kwargs` 一致。"""
    payload = {
        "video_url": f"https://www.bilibili.com/video/{task_id}",
        "platform": "bilibili",
        "quality": "1080p",
        "link": False,
        "screenshot": False,
        "model_name": "test-model",
        "provider_id": "1",
        "_format": ["markdown"],
        "scene": None,
        "detail": None,
        "extras": None,
        "video_understanding": False,
        "video_interval": 0,
        "grid_size": [],
        "sampling_mode": "interval",
        "max_frames": 60,
        "frames_per_second": 2,
        "frame_limit_mode": "total",
        "ocr_assist": None,
        "group_id": None,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """临时结果目录 + 一个只挂了 note 路由的 app；返回 (client, results_dir)。

    **两个 ``NOTE_OUTPUT_DIR`` 都要重定向。** 它是两个模块各自的全局量：
    ``app/routers/note.py:121`` 的字符串版本（``task_retry`` 通过延迟 import 读它）
    与 ``app/services/note.py:66`` 的 ``Path`` 版本（``NoteGenerator._update_status``
    真正往里写状态文件的那一个）。只改其中一个，测试就会一边读 tmp_path、一边把
    状态文件写进仓库的 ``note_results/``——断言失败在测试里，污染留在仓库里。
    """
    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))
    monkeypatch.setattr(note_service, "NOTE_OUTPUT_DIR", results_dir)

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app), results_dir


def _ok(response):
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


# --------------------------------------------------------------------------
# 1. 只有 FAILED 会被重试
# --------------------------------------------------------------------------


def test_only_failed_tasks_are_retried(env, monkeypatch):
    """SUCCESS 与在途任务都必须被跳过，且各自带上原因。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED", "转写失败")
    _write_status(results_dir, TASK_SUCCESS, "SUCCESS")
    _write_status(results_dir, TASK_BUSY, "DOWNLOADING")

    rows = {
        TASK_FAILED: {"task_id": TASK_FAILED, "payload_json": _write_payload(TASK_FAILED)},
        TASK_SUCCESS: {"task_id": TASK_SUCCESS, "payload_json": _write_payload(TASK_SUCCESS)},
        TASK_BUSY: {"task_id": TASK_BUSY, "payload_json": _write_payload(TASK_BUSY)},
    }
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks", lambda: list(rows.values())
    )
    dispatched = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", dispatched.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert data["requeued"] == [TASK_FAILED]
    skipped = {item["task_id"]: item["reason"] for item in data["skipped"]}
    assert "仍在执行" in skipped[TASK_BUSY]
    assert TASK_SUCCESS in skipped
    # 在途任务绝不能进分发池。
    assert len(dispatched) == 1


def test_missing_status_file_is_not_retried(env, monkeypatch):
    """状态文件读不到 = 不知道是什么状态，不猜（与启动恢复的取舍相反）。

    启动恢复把「读不到」当「需要恢复」（进程在写第一次状态前就被杀了）；重试这里
    进程活得好好的，读不到只说明这个任务从没真正开始过，重试它没有依据。
    """
    client, results_dir = env
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [{"task_id": "ghost", "payload_json": _write_payload("ghost")}],
    )
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert data["requeued"] == []
    assert data["skipped"][0]["task_id"] == "ghost"
    assert "尚未开始" in data["skipped"][0]["reason"]


# --------------------------------------------------------------------------
# 2. 原地重试：task_id 不变、参数沿用 payload_json
# --------------------------------------------------------------------------


def test_retry_reuses_task_id_and_stored_payload(env, monkeypatch):
    """重试用同一个 task_id 与创建时存下的参数，而不是默认值。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED", "转写失败")
    stored = _write_payload(
        TASK_FAILED,
        max_frames=123,
        sampling_mode="count",
        ocr_assist=True,
        model_name="stored-model",
        group_id="group-7",
    )
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [{"task_id": TASK_FAILED, "payload_json": stored, "platform": "bilibili"}],
    )
    dispatched = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", dispatched.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert data["requeued"] == [TASK_FAILED]
    assert len(dispatched) == 1
    kwargs = dispatched[0]
    # task_id 复用，不是新生成的 uuid。
    assert kwargs["task_id"] == TASK_FAILED
    # 参数取自 payload_json，而不是 run_note_task 的默认值。
    assert kwargs["max_frames"] == 123
    assert kwargs["sampling_mode"] == "count"
    assert kwargs["ocr_assist"] is True
    assert "model_name" not in kwargs
    assert "provider_id" not in kwargs
    # 分组归属保留。
    assert kwargs["group_id"] == "group-7"


def test_retry_does_not_create_a_new_task_row(env, monkeypatch):
    """重试只改状态，**不**新增 DB 行 —— 列表里不该多出一条。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED")
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [{"task_id": TASK_FAILED, "payload_json": _write_payload(TASK_FAILED)}],
    )
    monkeypatch.setattr(note_module, "_dispatch_note_task", lambda kwargs: None)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )
    inserted = []
    monkeypatch.setattr(
        "app.db.video_task_dao.insert_video_task",
        lambda *a, **kw: inserted.append((a, kw)),
    )

    _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert inserted == []


def test_retry_writes_pending_status(env, monkeypatch):
    """重试后状态文件必须变回 PENDING，否则界面还显示「失败」。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED", "转写失败")
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [{"task_id": TASK_FAILED, "payload_json": _write_payload(TASK_FAILED)}],
    )
    monkeypatch.setattr(note_module, "_dispatch_note_task", lambda kwargs: None)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    status_path = results_dir / f"{TASK_FAILED}.status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["status"] == "PENDING"
    assert "重试" in payload["message"]


# --------------------------------------------------------------------------
# 3. 范围：all / group
# --------------------------------------------------------------------------


def test_scope_group_only_retries_that_group(env, monkeypatch):
    """scope=group 时只重试该组内的失败任务，其它组一律不碰。"""
    client, results_dir = env
    _write_status(results_dir, "in-group", "FAILED")
    _write_status(results_dir, "other-group", "FAILED")
    monkeypatch.setattr(
        note_module,
        "_dispatch_note_task",
        lambda kwargs: None,
    )
    # 组内成员由 DAO 给出；这里只 mock 它，重试本身仍走真实实现。
    monkeypatch.setattr(
        "app.db.note_group_dao.list_task_ids_in_group",
        lambda group_id: ["in-group"] if group_id == "g1" else [],
    )
    monkeypatch.setattr(
        "app.db.video_task_dao.get_video_task",
        lambda task_id: {
            "task_id": task_id,
            "payload_json": _write_payload(task_id),
            "platform": "bilibili",
        },
    )
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(
        client.post("/api/retry_failed_tasks", json={"scope": "group", "group_id": "g1"})
    )

    assert data["scope"] == "group"
    assert data["group_id"] == "g1"
    assert data["requeued"] == ["in-group"]


def test_group_scope_accepts_the_orm_row_the_dao_really_returns(env, monkeypatch):
    """``get_video_task`` 返回的是 ORM 对象，不是 dict —— 按分组重试必须照样能跑。

    真实故障：``scope="group"`` 走 ``get_video_task``，拿到 ``VideoTask`` 实例后被
    ``_select_retryable`` 按 dict 访问，整个请求抛
    ``AttributeError: 'VideoTask' object has no attribute 'get'``，一条任务都没重排，
    用户看到的是「重试失败」。

    这个用例存在的理由就是上面那条测试喂进去的假行是 **dict** —— 与真实 DAO 的返回
    类型不一致，所以它永远发现不了这个 bug。这里刻意返回真正的 ``VideoTask`` 实例
    （不落库，只赋属性；``_row_to_dict`` 只读属性）。
    """
    client, results_dir = env
    _write_status(results_dir, "orm-task", "FAILED")
    monkeypatch.setattr(
        "app.db.note_group_dao.list_task_ids_in_group", lambda group_id: ["orm-task"]
    )
    orm_row = VideoTask(
        video_id="BV1orm",
        platform="bilibili",
        task_id="orm-task",
        payload_json=_write_payload("orm-task"),
    )
    monkeypatch.setattr("app.db.video_task_dao.get_video_task", lambda task_id: orm_row)
    dispatched = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", dispatched.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(
        client.post("/api/retry_failed_tasks", json={"scope": "group", "group_id": "g1"})
    )

    assert data["requeued"] == ["orm-task"]
    assert data["skipped"] == []
    assert len(dispatched) == 1


def test_scope_group_with_null_group_id_means_ungrouped(env, monkeypatch):
    """group_id=null 是「未分组」，不是「全部」—— 传错会误伤别的组。"""
    client, _results_dir = env
    seen = {}
    monkeypatch.setattr(
        "app.db.note_group_dao.list_task_ids_in_group",
        lambda group_id: seen.setdefault("group_id", group_id) or [],
    )
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "group"}))

    assert seen["group_id"] is None
    assert data["group_id"] is None


def test_invalid_scope_is_rejected(env):
    """scope 拼错时必须报错，而不是静默按 all 处理 —— 那会重试整个库。"""
    client, _results_dir = env
    body = client.post("/api/retry_failed_tasks", json={"scope": "everything"}).json()
    assert body["code"] == 400


# --------------------------------------------------------------------------
# 4. 门禁
# --------------------------------------------------------------------------


def test_transcriber_not_ready_blocks_retry(env, monkeypatch):
    """转写模型没就绪时拒绝重试：否则只会原样再失败一遍。"""
    client, _results_dir = env
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": False,
            "reason": "转写模型未就绪",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": True,
        },
    )
    called = []
    monkeypatch.setattr(
        task_retry, "retry_failed_tasks", lambda ids: called.append(ids) or {}
    )

    body = client.post("/api/retry_failed_tasks", json={"scope": "all"}).json()

    assert body["code"] == 300102
    assert body["data"]["reason"] == "transcriber_model_not_ready"
    assert called == []


def test_insufficient_disk_blocks_retry(env, monkeypatch):
    """磁盘不够时拒绝整批（重试同样要重新下载媒体）。"""
    client, _results_dir = env
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )
    monkeypatch.setattr(note_module, "_check_disk_space", lambda: "剩余磁盘空间不足")
    called = []
    monkeypatch.setattr(
        task_retry, "retry_failed_tasks", lambda ids: called.append(ids) or {}
    )

    body = client.post("/api/retry_failed_tasks", json={"scope": "all"}).json()

    assert body["code"] == 300104
    assert body["data"]["reason"] == "insufficient_disk_space"
    assert called == []


def test_user_retry_resets_circuit_breaker(env, monkeypatch):
    """用户主动重试 = 熔断复位信号（与 /generate_notes 一致）。"""
    client, _results_dir = env
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )
    monkeypatch.setattr(
        note_module,
        "_dispatch_note_task",
        lambda kwargs: None,
    )
    monkeypatch.setattr("app.db.video_task_dao.list_recoverable_tasks", lambda: [])

    breaker = note_module._get_circuit_breaker()
    for _ in range(10):
        breaker.record_failure()
    assert breaker.is_paused() is True

    _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert breaker.is_paused() is False


# --------------------------------------------------------------------------
# 5. 降级：payload_json 缺失时按 video_id 重建
# --------------------------------------------------------------------------


def test_missing_payload_falls_back_to_video_id(env, monkeypatch):
    """没有 payload_json 的老库行：按 bilibili video_id 重建一个最小参数集。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED")
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [
            {
                "task_id": TASK_FAILED,
                "video_id": "BV1xx411c7mD_p3",
                "platform": "bilibili",
                "payload_json": None,
                "group_id": None,
            }
        ],
    )
    dispatched = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", dispatched.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert data["requeued"] == [TASK_FAILED]
    # _p3 要变成 ?p=3，否则重试的是第 1 集，用户拿到的笔记不对。
    assert dispatched[0]["video_url"] == "https://www.bilibili.com/video/BV1xx411c7mD?p=3"


def test_unrebuildable_payload_is_reported_not_silently_dropped(env, monkeypatch):
    """既没有 payload_json、也无法按 video_id 重建时，必须带原因汇报。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED")
    monkeypatch.setattr(
        "app.db.video_task_dao.list_recoverable_tasks",
        lambda: [
            {
                "task_id": TASK_FAILED,
                "video_id": "not-a-bvid",
                "platform": "douyin",
                "payload_json": None,
            }
        ],
    )
    called = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", called.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "all"}))

    assert data["requeued"] == []
    assert called == []
    assert data["skipped"][0]["task_id"] == TASK_FAILED
    assert "缺少可用的生成参数" in data["skipped"][0]["reason"]


def test_reported_missing_task_ids(env, monkeypatch):
    """库里查不到的 id 要如实汇报 —— 说明它在别处已被删除。"""
    client, _results_dir = env
    monkeypatch.setattr(
        "app.db.video_task_dao.get_video_task", lambda task_id: None
    )
    monkeypatch.setattr(
        "app.db.note_group_dao.list_task_ids_in_group", lambda group_id: ["gone"]
    )
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "group", "group_id": "g1"}))

    assert data["requeued"] == []
    assert data["missing"] == ["gone"]


def test_duplicate_task_ids_are_requeued_once(env, monkeypatch):
    """同一个 id 传两次只能入队一次，否则同一个 task_id 会被跑两遍。"""
    client, results_dir = env
    _write_status(results_dir, TASK_FAILED, "FAILED")
    monkeypatch.setattr(
        "app.db.video_task_dao.get_video_task",
        lambda task_id: {
            "task_id": task_id,
            "payload_json": _write_payload(task_id),
            "platform": "bilibili",
        },
    )
    monkeypatch.setattr(
        "app.db.note_group_dao.list_task_ids_in_group",
        lambda group_id: [TASK_FAILED, TASK_FAILED, TASK_FAILED],
    )
    dispatched = []
    monkeypatch.setattr(note_module, "_dispatch_note_task", dispatched.append)
    monkeypatch.setattr(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        lambda self: {
            "ready": True,
            "reason": "",
            "transcriber_type": "local",
            "model_size": "small",
            "downloading": False,
        },
    )

    data = _ok(client.post("/api/retry_failed_tasks", json={"scope": "group", "group_id": "g1"}))

    assert data["requeued"] == [TASK_FAILED]
    assert len(dispatched) == 1


# --------------------------------------------------------------------------
# 6. 契约：路由真的挂在生产 app 上
# --------------------------------------------------------------------------


def test_retry_route_is_registered_on_production_app():
    """本文件的测试自建 FastAPI()，但生产挂载在 app/__init__.py 的 create_app 里。

    「测试挂法与生产一致」这个前提本身要验 —— 否则测试全绿而生产 404。
    """
    import contextlib

    from app import create_app

    app = create_app(contextlib.nullcontext)
    # 用 getattr 取值，而不是直接 route.path / route.methods：app.routes 是 BaseRoute
    # 的异构列表，Mount 之类没有这两个属性，写属性访问静态检查会直接报错。
    paths = set()
    for route in app.routes:
        if "POST" not in (getattr(route, "methods", None) or set()):
            continue
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    assert "/api/retry_failed_tasks" in paths
