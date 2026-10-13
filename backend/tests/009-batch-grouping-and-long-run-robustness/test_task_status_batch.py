"""spec 009 ticket 06：批量任务状态端点。

批量轮询的价值全在「一次请求拿回全部待办」+「不带整份 markdown」。这里把两件事
都钉死，另外钉住「未知 id 返回 null 而不是报错」—— 轮询期间任务可能刚被删掉。
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import note as note_module
from app.routers.note import BatchStatusRequest, _read_task_status


@pytest.fixture
def env(tmp_path, monkeypatch):
    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))
    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app), results_dir


def _write(results_dir, task_id, payload, suffix=".status.json"):
    (results_dir / f"{task_id}{suffix}").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _ok(response):
    body = response.json()
    assert body["code"] == 0, body
    return body["data"]


def test_batch_returns_states_for_all_ids(env):
    client, results_dir = env
    _write(results_dir, "t1", {"status": "TRANSCRIBING", "progress": 40})
    _write(results_dir, "t2", {"status": "SUCCESS", "progress": 100})
    _write(results_dir, "t2", {"markdown": "x" * 5000}, suffix=".json")

    data = _ok(client.post("/api/task_status/batch", json={"task_ids": ["t1", "t2"]}))
    assert set(data["states"]) == {"t1", "t2"}
    assert data["states"]["t1"]["status"] == "TRANSCRIBING"
    assert data["states"]["t1"]["progress"] == 40
    assert data["states"]["t2"]["status"] == "SUCCESS"


def test_batch_never_returns_heavy_result_payload(env):
    """这是批量端点存在的理由：成功任务不能把整份 markdown 塞进每轮响应。"""
    client, results_dir = env
    _write(results_dir, "t1", {"status": "SUCCESS", "progress": 100})
    _write(
        results_dir, "t1", {"markdown": "x" * 100000, "transcript": {}}, suffix=".json"
    )

    data = _ok(client.post("/api/task_status/batch", json={"task_ids": ["t1"]}))
    state = data["states"]["t1"]
    assert "result" not in state
    assert "markdown" not in state
    # 响应体必须远小于原始结果（否则等于没省）
    assert len(json.dumps(data)) < 2000


def test_single_status_endpoint_still_returns_result(env):
    """单任务端点保持原样：详情页要用它拿 markdown。"""
    client, results_dir = env
    _write(results_dir, "t1", {"status": "SUCCESS", "progress": 100})
    _write(results_dir, "t1", {"markdown": "# hi"}, suffix=".json")

    data = _ok(client.get("/api/task_status/t1"))
    assert data["result"]["markdown"] == "# hi"


def test_unknown_id_returns_none_not_error(env, monkeypatch):
    """轮询期间任务可能刚被删 —— 报错会让前端把整轮结果丢掉。

    这里的「未知」必须真的未知：库里也没有这条任务行。patch 掉查库是为了不碰
    用户真实的 ``bili_note.db``（本文件其余用例都只用临时结果目录）。
    """
    client, _results_dir = env
    monkeypatch.setattr(note_module, "_task_row_exists", lambda _tid: False)
    data = _ok(client.post("/api/task_status/batch", json={"task_ids": ["nope"]}))
    assert data["states"]["nope"] is None


def test_queued_task_without_files_still_reports_pending(env, monkeypatch):
    """刚入队、文件还没落盘的任务不能被报成 null（前端会以为任务消失了）。"""
    client, _results_dir = env
    monkeypatch.setattr(note_module, "_task_row_exists", lambda _tid: True)
    data = _ok(client.post("/api/task_status/batch", json={"task_ids": ["t-queued"]}))
    assert data["states"]["t-queued"]["status"] == "PENDING"


def test_duplicate_ids_are_deduplicated(env):
    client, results_dir = env
    _write(results_dir, "t1", {"status": "PENDING", "progress": 0})
    data = _ok(
        client.post(
            "/api/task_status/batch",
            json={"task_ids": ["t1", "t1", " t1 "]},
        )
    )
    assert list(data["states"]) == ["t1"]


def test_empty_id_list_is_ok(env):
    client, _results_dir = env
    data = _ok(client.post("/api/task_status/batch", json={"task_ids": []}))
    assert data["states"] == {}


def test_too_many_ids_rejected(env):
    client, _results_dir = env
    body = client.post(
        "/api/task_status/batch",
        json={"task_ids": [f"t{i}" for i in range(1001)]},
    ).json()
    assert body["code"] == 400


def test_invalid_id_shape_is_rejected_by_reader(env):
    """路径穿越/非法字符不能变成文件读取。"""
    _client, results_dir = env
    assert _read_task_status("../../etc/passwd", include_result=False) is None
    assert _read_task_status("a/b", include_result=False) is None
    assert _read_task_status("", include_result=False) is None


def test_task_without_status_file_reports_pending(env):
    """只有结果文件、没有状态文件时按已完成返回；两个都没有则按排队中。"""
    _client, results_dir = env
    _write(results_dir, "t-done", {"markdown": "# x"}, suffix=".json")
    done = _read_task_status("t-done", include_result=False)
    assert done is not None
    assert done["status"] == "SUCCESS"

    queued = _read_task_status("t-queued", include_result=False)
    assert queued is not None
    assert queued["status"] == "PENDING"
    assert queued["message"] == "任务排队中"


def test_corrupt_status_file_does_not_raise(env):
    _client, results_dir = env
    (results_dir / "t-bad.status.json").write_text("{not json", encoding="utf-8")
    assert _read_task_status("t-bad", include_result=False) is None


def test_batch_request_model_shape():
    req = BatchStatusRequest(task_ids=["a", "b"])
    assert req.task_ids == ["a", "b"]
