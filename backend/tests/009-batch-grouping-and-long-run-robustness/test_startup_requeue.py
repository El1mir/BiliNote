"""spec 009 ticket 03：启动时重新入队在途任务。"""

import json
import os
from unittest import mock

import pytest

from app.services import task_recovery


def _write_status(results_dir, task_id, status):
    path = os.path.join(str(results_dir), f"{task_id}.status.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"status": status}, f)


@pytest.fixture()
def results_dir(tmp_path, monkeypatch):
    d = tmp_path / "note_results"
    d.mkdir()
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(d))
    monkeypatch.setattr(task_recovery, "_note_output_dir", lambda: str(d))
    return d


def _rows(*specs):
    """specs: (task_id, video_id, platform, status_or_None, payload_json)"""
    return [
        {
            "task_id": tid,
            "video_id": vid,
            "platform": plat,
            "group_id": None,
            "payload_json": payload,
            "created_at": None,
        }
        for tid, vid, plat, _status, payload in specs
    ]


def _run(rows, results_dir, statuses, paused=False):
    """跑一次恢复；statuses 是 {task_id: status}（不写文件 = 状态未知）。"""
    for tid, status in statuses.items():
        _write_status(results_dir, tid, status)
    dispatched = []
    with (
        mock.patch("app.db.video_task_dao.list_recoverable_tasks", return_value=rows),
        mock.patch.object(
            task_recovery, "_read_status", side_effect=lambda tid: statuses.get(tid)
        ),
        mock.patch(
            "app.routers.note._dispatch_note_task",
            side_effect=lambda kw: dispatched.append(kw),
        ),
        mock.patch("app.routers.note._get_circuit_breaker") as breaker,
        mock.patch("app.services.note.NoteGenerator"),
    ):
        breaker.return_value.is_paused.return_value = paused
        stats = task_recovery.recover_interrupted_tasks()
    return stats, dispatched


def test_requeues_in_flight_tasks(results_dir):
    payload = json.dumps(
        {
            "video_url": "https://www.bilibili.com/video/BV1a",
            "platform": "bilibili",
            "quality": "fast",
            "model_name": "m",
            "provider_id": "p",
            "group_id": "gid-1",
        }
    )
    rows = _rows(
        ("t-pending", "BV1a", "bilibili", "PENDING", payload),
        ("t-download", "BV1b", "bilibili", "DOWNLOADING", payload),
    )
    stats, dispatched = _run(
        rows, results_dir, {"t-pending": "PENDING", "t-download": "DOWNLOADING"}
    )

    assert stats["requeued"] == 2
    assert {kw["task_id"] for kw in dispatched} == {"t-pending", "t-download"}
    assert all(kw["group_id"] == "gid-1" for kw in dispatched)
    assert all("model_name" not in kw and "provider_id" not in kw for kw in dispatched)


def test_failed_and_success_are_not_requeued(results_dir):
    """FAILED 是已有结论的任务，重启后不该自己活过来（用户决策 m00235）。"""
    payload = json.dumps({"video_url": "https://x/BV1a", "platform": "bilibili"})
    rows = _rows(
        ("t-failed", "BV1a", "bilibili", "FAILED", payload),
        ("t-success", "BV1b", "bilibili", "SUCCESS", payload),
        ("t-pending", "BV1c", "bilibili", "PENDING", payload),
    )
    stats, dispatched = _run(
        rows,
        results_dir,
        {
            "t-failed": "FAILED",
            "t-success": "SUCCESS",
            "t-pending": "PENDING",
        },
    )

    assert stats["skipped_finished"] == 2
    assert stats["requeued"] == 1
    assert dispatched[0]["task_id"] == "t-pending"


def test_missing_status_file_is_treated_as_recoverable(results_dir):
    """状态文件读不到 = 进程在写第一次状态前就被杀了，恰恰最该恢复。"""
    rows = _rows(("t-nostatus", "BV1a", "bilibili", None, None))
    stats, dispatched = _run(rows, results_dir, {})

    assert stats["requeued"] == 1
    # 没有 payload_json 时按 video_id 重建 bilibili URL
    assert dispatched[0]["video_url"] == "https://www.bilibili.com/video/BV1a"


def test_part_page_url_is_rebuilt_from_video_id(results_dir):
    rows = _rows(("t-p2", "BV1abc_p3", "bilibili", None, None))
    _stats, dispatched = _run(rows, results_dir, {})
    assert dispatched[0]["video_url"] == "https://www.bilibili.com/video/BV1abc?p=3"


def test_unrecoverable_row_is_skipped_not_run_with_defaults(results_dir):
    """重建不出参数的行要跳过并计数，不能拿默认参数硬跑。"""
    rows = _rows(("t-bad", "not-a-bvid", "bilibili", None, None))
    stats, dispatched = _run(rows, results_dir, {})

    assert stats["requeued"] == 0
    assert stats["skipped_invalid"] == 1
    assert dispatched == []


def test_unknown_status_is_not_requeued(results_dir):
    rows = _rows(("t-weird", "BV1a", "bilibili", "SOMETHING_NEW", None))
    stats, dispatched = _run(rows, results_dir, {"t-weird": "SOMETHING_NEW"})
    assert stats["requeued"] == 0
    assert dispatched == []


def test_circuit_breaker_paused_blocks_recovery(results_dir):
    """熔断暂停期间不恢复 —— 否则等于绕过熔断（用户决策 m00235）。"""
    rows = _rows(("t-pending", "BV1a", "bilibili", "PENDING", None))
    stats, dispatched = _run(rows, results_dir, {"t-pending": "PENDING"}, paused=True)
    assert stats["requeued"] == 0
    assert dispatched == []


def test_broken_payload_falls_back_to_video_id(results_dir):
    rows = _rows(("t-broken", "BV1zz", "bilibili", "PENDING", "{not json"))
    stats, dispatched = _run(rows, results_dir, {"t-broken": "PENDING"})
    assert stats["requeued"] == 1
    assert dispatched[0]["video_url"] == "https://www.bilibili.com/video/BV1zz"


def test_start_recovery_thread_does_not_raise_on_failure():
    """恢复线程炸了也不能影响启动。"""
    with mock.patch.object(
        task_recovery, "recover_interrupted_tasks", side_effect=RuntimeError("boom")
    ):
        thread = task_recovery.start_recovery_thread()
    thread.join(timeout=5)
    assert not thread.is_alive()
