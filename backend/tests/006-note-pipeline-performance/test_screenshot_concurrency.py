"""spec 006 ticket 03 + spec 005：截图生成并发、进度回报与顺序保持。

截图是纯等待型工作（每个标记一次 ffmpeg），因此并发执行：
  * 并发数 > 1 时确实同时跑多个 ffmpeg；
  * 回填顺序严格按标记出现顺序（URL 位置不能乱）；
  * stage_progress 从 0 单调走到 100，且 detail/task_id 与真实任务一致；
  * 失败时保持旧语义（返回 None，日志记录）。
"""
import threading
import time
from pathlib import Path

from app.enmus.task_status_enums import TaskStatus
from app.services import note as note_module
from app.services.note import NoteGenerator

MARKDOWN = "S1 *Screenshot-00:01 S2 Screenshot-[00:02] S3 *Screenshot-00:03 S4 Screenshot-[00:04]"


def _generator(tmp_path, monkeypatch, delay=0.0, fail=False):
    generator = object.__new__(NoteGenerator)
    statuses = []
    calls = []
    lock = threading.Lock()
    state = {"running": 0, "peak": 0}

    def fake_update_status(
        task_id, status, message=None, *, stage=None, progress=None, stage_progress=None, detail=None
    ):
        with lock:
            statuses.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "message": message,
                    "stage": stage,
                    "progress": progress,
                    "stage_progress": stage_progress,
                    "detail": detail,
                }
            )

    def fake_generate_screenshot(video_path, output_dir, ts, index):
        with lock:
            calls.append((video_path, output_dir, ts, index))
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        try:
            if delay:
                time.sleep(delay)
            if fail:
                raise RuntimeError("ffmpeg 挂了")
            return str(Path(output_dir) / f"screenshot_{index:03}.jpg")
        finally:
            with lock:
                state["running"] -= 1

    generator._update_status = fake_update_status
    monkeypatch.setattr(note_module, "generate_screenshot", fake_generate_screenshot)
    monkeypatch.setattr(note_module, "IMAGE_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(note_module, "IMAGE_BASE_URL", "/static/screenshots")
    return generator, statuses, calls, state


def test_no_markers_returns_markdown_unchanged(tmp_path, monkeypatch):
    generator, statuses, calls, _ = _generator(tmp_path, monkeypatch)

    assert generator._insert_screenshots("普通正文", Path("v.mp4"), task_id="task-1") == "普通正文"
    assert calls == []
    assert statuses == []


def test_screenshots_are_replaced_in_marker_order(tmp_path, monkeypatch):
    generator, statuses, calls, _ = _generator(tmp_path, monkeypatch, delay=0.02)

    result = generator._insert_screenshots(MARKDOWN, Path("v.mp4"), task_id="task-1")

    assert result is not None
    assert len(calls) == 4
    assert sorted(call[2] for call in calls) == [1, 2, 3, 4]
    # 截图索引用 enumerate(matches)（0 起），因此文件名是 screenshot_000..003
    positions = [result.index(f"/static/screenshots/screenshot_{i:03}.jpg") for i in range(4)]
    assert positions == sorted(positions), "URL 顺序必须与标记出现顺序一致"
    assert result.count("![](") == 4


def test_screenshot_progress_reaches_100_with_real_task_id(tmp_path, monkeypatch):
    generator, statuses, _, _ = _generator(tmp_path, monkeypatch, delay=0.02)

    generator._insert_screenshots(MARKDOWN, Path("v.mp4"), task_id="task-1")

    progress_statuses = [s for s in statuses if s["detail"] and s["detail"].get("unit") == "screenshots"]
    assert progress_statuses, "截图阶段需要上报可计算的进度"
    assert all(s["task_id"] == "task-1" for s in statuses)
    assert all(s["status"] == TaskStatus.FORMATTING for s in statuses)
    assert progress_statuses[0]["stage_progress"] == 0
    assert progress_statuses[-1]["stage_progress"] == 100
    assert progress_statuses[-1]["detail"] == {"current": 4, "total": 4, "unit": "screenshots"}
    values = [s["stage_progress"] for s in progress_statuses]
    assert values == sorted(values), "截图进度不能回退"


def test_screenshot_generation_runs_concurrently(tmp_path, monkeypatch):
    generator, _, _, state = _generator(tmp_path, monkeypatch, delay=0.05)

    generator._insert_screenshots(MARKDOWN, Path("v.mp4"), task_id="task-1")

    assert state["peak"] >= 2, "多个标记应并发截图，而不是逐个串行等待 ffmpeg"


def test_screenshot_failure_keeps_old_semantics(tmp_path, monkeypatch):
    generator, _, _, _ = _generator(tmp_path, monkeypatch, fail=True)

    assert generator._insert_screenshots(MARKDOWN, Path("v.mp4"), task_id="task-1") is None
