"""spec 001 §12 追加：重试时也要防同一 task_id 并发跑两遍。

背景（真实日志）：任务在跑时前端因状态轮询超时误判为失败 → 出现「重试」按钮 →
点下去带同一个 task_id 重新提交，而重试分支原先跳过了「进行中」检查 →
同一个 task_id 被并发执行两遍：yt-dlp 重复下载、抽帧目录互踩、
状态文件 .tmp 抢锁报 Permission denied。
"""
import json

from app.routers import note as note_router


def _write_status(tmp_path, task_id: str, status: str):
    (tmp_path / f"{task_id}.status.json").write_text(
        json.dumps({"status": status}, ensure_ascii=False), encoding="utf-8"
    )


def test_is_task_id_in_flight_detects_running_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(note_router, "NOTE_OUTPUT_DIR", str(tmp_path))

    # 没有状态文件
    assert note_router._is_task_id_in_flight("t1") is False

    for status in ("PENDING", "PARSING", "DOWNLOADING", "TRANSCRIBING", "SUMMARIZING", "SAVING"):
        _write_status(tmp_path, "t1", status)
        assert note_router._is_task_id_in_flight("t1") is True, status

    for status in ("SUCCESS", "FAILED", "unknown-status"):
        _write_status(tmp_path, "t1", status)
        assert note_router._is_task_id_in_flight("t1") is False, status


def test_is_task_id_in_flight_handles_bad_json_and_empty_id(tmp_path, monkeypatch):
    monkeypatch.setattr(note_router, "NOTE_OUTPUT_DIR", str(tmp_path))

    assert note_router._is_task_id_in_flight("") is False

    (tmp_path / "broken.status.json").write_text("not json", encoding="utf-8")
    assert note_router._is_task_id_in_flight("broken") is False
