"""spec 022 W1：闸门是唯一并发上限 + 合并任务真并发 + 429 断点续跑。

验收对应用户案卷第 1/2/3 条：

1. 设置并行 8 时 10 条假任务最大在途 8；设 3 时为 3（没有隐藏的 5 上限）。
2. 10 条合并任务 gate=4 时最大在途 4，章节顺序严格等于输入顺序，进度单调到 10/10。
3. 第 5 条起模拟 429 停放：1-4 的结果在断点里，恢复后 1-4 不重新生成，5-10 继续,
   最终 10 条齐全。

合并任务用假 NoteGenerator 替换下载/转写/总结，其余走的都是真实代码：
真实闸门、真实断点读写、真实 build_merged_markdown、真实进度写入。
"""

import re
import threading
import time

import pytest

from app.enmus.note_enums import DownloadQuality
from app.models.audio_model import AudioDownloadResult
from app.models.notes_model import NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.routers import note as note_module


class _Limit:
    """可变的并行上限，替代 _safe_max_parallel_notes() 的返回值。"""

    def __init__(self, value):
        self.value = value


@pytest.fixture
def gate_env(monkeypatch, tmp_path):
    """每个用例一张干净的闸门 + 可控的并行上限 + 隔离的输出目录。"""
    holder = _Limit(2)
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    monkeypatch.setattr(note_module, "_safe_max_parallel_notes", lambda: holder.value)
    note_dir = tmp_path / "note_results"
    note_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(note_dir))
    yield holder
    # 探针在「最后一条进入任务体」时就返回，可能仍有任务在闸门内收尾；
    # 留 2s 归还窗口再断言，避免把正常收尾误报成名额泄漏。
    gate = note_module._PARALLEL_GATE
    if gate is not None:
        deadline = time.monotonic() + 2
        while gate.active and time.monotonic() < deadline:
            time.sleep(0.02)
        assert gate.active == 0, f"用例结束时闸门仍有 {gate.active} 个名额未归还"


class _Probe:
    """记录同时在执行的线程数、进入次数。"""

    def __init__(self, delay=0.03):
        self._lock = threading.Lock()
        self._delay = delay
        self.current = 0
        self.max_seen = 0
        self.entered = 0
        self.finished = 0

    def body(self):
        with self._lock:
            self.current += 1
            self.entered += 1
            self.max_seen = max(self.max_seen, self.current)
        try:
            time.sleep(self._delay)
        finally:
            with self._lock:
                self.current -= 1
                self.finished += 1


# ---------------------------------------------------------------------------
# 1) 闸门就是上限：设 8 得 8，设 3 得 3
# ---------------------------------------------------------------------------


def _run_dispatch_batch(monkeypatch, count):
    probe = _Probe(delay=0.15)

    def fake_run_note_task(**kwargs):
        note_module._run_with_parallel_gate(probe.body)

    monkeypatch.setattr(note_module, "run_note_task", fake_run_note_task)
    for index in range(count):
        note_module._dispatch_note_task({"task_id": f"t{index}"})

    deadline = time.monotonic() + 20
    while probe.finished < count and time.monotonic() < deadline:
        time.sleep(0.05)
    assert probe.finished == count, f"{count} 条任务没能在 20s 内跑完"
    # 任务体返回后闸门才 release，稍等一拍再让 fixture 断言名额归零。
    time.sleep(0.2)
    return probe


def test_gate_allows_eight_concurrent_tasks(gate_env, monkeypatch):
    gate_env.value = 8
    probe = _run_dispatch_batch(monkeypatch, count=10)
    assert probe.max_seen == 8, f"设置 8 时最大在途应为 8，实际 {probe.max_seen}（疑似仍有隐藏上限）"


def test_gate_respects_lower_setting(gate_env, monkeypatch):
    gate_env.value = 3
    probe = _run_dispatch_batch(monkeypatch, count=10)
    assert probe.max_seen == 3, f"设置 3 时最大在途应为 3，实际 {probe.max_seen}"


# ---------------------------------------------------------------------------
# 2/3) 合并任务：并发扇出、顺序、进度、断点
# ---------------------------------------------------------------------------


class _FakeGenerator:
    """替换 NoteGenerator：状态写入真实记录，生成结果立即可控。"""

    probe: _Probe | None = None
    status_log: list = []
    generate_calls: list = []
    server_429_from_index: int | None = None
    park_calls: list = []

    def __init__(self):
        self.last_error_rate_limited = False
        self.last_error_non_retryable = False

    def _update_status(self, task_id, status, message=None, **kwargs):
        type(self).status_log.append(
            {
                "task_id": task_id,
                "status": getattr(status, "value", str(status)),
                "message": message or "",
                "progress": kwargs.get("progress"),
            }
        )

    def generate(self, **kwargs):
        task_id = str(kwargs.get("task_id") or "")
        video_url = str(kwargs.get("video_url") or "")
        index = int(re.search(r"-s(\d+)$", task_id).group(1))
        type(self).generate_calls.append(index)

        if (
            type(self).server_429_from_index is not None
            and index >= type(self).server_429_from_index
        ):
            self.last_error_rate_limited = True
            return None

        probe = type(self).probe
        if probe is not None:
            probe.body()
        return NoteResult(
            markdown=f"# 视频 {index}\n\n正文 {index}",
            transcript=TranscriptResult(
                language="zh",
                full_text=f"转写 {index}",
                segments=[TranscriptSegment(start=0.0, end=1.0, text=f"转写 {index}")],
            ),
            audio_meta=AudioDownloadResult(
                file_path=f"/tmp/{index}.mp3",
                title=f"视频{index}",
                duration=float(index),
                cover_url=None,
                platform="bilibili",
                video_id=f"v{index}",
                raw_info={},
            ),
        )


@pytest.fixture
def merge_env(gate_env, monkeypatch):
    """合并任务所需的全部外部副作用都替换成内存记录。"""
    _FakeGenerator.probe = None
    _FakeGenerator.status_log = []
    _FakeGenerator.generate_calls = []
    _FakeGenerator.server_429_from_index = None
    _FakeGenerator.park_calls = []

    saved = {}
    monkeypatch.setattr(note_module, "NoteGenerator", _FakeGenerator)
    monkeypatch.setattr(
        note_module, "save_note_to_file", lambda task_id, note: saved.setdefault(task_id, note)
    )
    monkeypatch.setattr(note_module, "_cleanup_merged_subtask_files", lambda sub_task_id: None)
    monkeypatch.setattr(note_module, "_enforce_cache_limit_in_background", lambda: None)
    monkeypatch.setattr(note_module, "_park_rate_limited_task", lambda task_id, kwargs: _FakeGenerator.park_calls.append(task_id))
    monkeypatch.setattr(
        note_module,
        "_get_circuit_breaker",
        lambda: type("_Breaker", (), {"record_success": lambda self: None})(),
    )
    return saved


def _items(count):
    return [
        {"url": f"https://example.com/v{i}", "title": f"视频{i}", "video_id": f"v{i}"}
        for i in range(1, count + 1)
    ]


def _run_merge(task_id, items, gate_limit=4):
    return note_module._run_merged_note_task(
        task_id=task_id,
        items=items,
        merge_title="合集",
        merge_polish=False,
        model_name=None,
        provider_id=None,
        platform="bilibili",
        quality=DownloadQuality.fast,
        link=False,
        screenshot=False,
        _format=None,
        scene=None,
        detail=None,
        extras=None,
        video_understanding=False,
        video_interval=1,
        grid_size="3x3",
        sampling_mode="uniform",
        max_frames=10,
        frames_per_second=1,
        frame_limit_mode="uniform",
        ocr_assist=False,
        park_kwargs={"task_id": task_id},
    )


def test_merge_fans_out_up_to_gate_and_keeps_input_order(merge_env, gate_env):
    gate_env.value = 4
    _FakeGenerator.probe = _Probe(delay=0.05)

    _run_merge("merge-order", _items(10))

    assert _FakeGenerator.probe.max_seen == 4, (
        f"gate=4 时合并任务最大在途应为 4，实际 {_FakeGenerator.probe.max_seen}"
        "（串行说明扇出没生效，>4 说明绕过了闸门）"
    )

    note = merge_env["merge-order"]
    assert note.markdown.count("\n## ") >= 10, "10 条都应该出现在合并正文里"
    order = [note.markdown.index(f"视频{i}\n") if f"视频{i}\n" in note.markdown else note.markdown.index(f"视频{i}") for i in range(1, 11)]
    assert order == sorted(order), f"章节顺序必须等于输入顺序，实际 {order}"

    progress = [
        int(match.group(1))
        for entry in _FakeGenerator.status_log
        if (match := re.search(r"合并生成 (\d+)/10", entry["message"]))
    ]
    assert progress == sorted(progress), f"进度必须单调递增，实际 {progress}"
    assert progress[-1] == 10, f"最后一条进度应为 10/10，实际 {progress}"
    assert any(entry["message"].startswith("已合并 10/10") for entry in _FakeGenerator.status_log)


def test_merge_429_parks_and_resumes_from_checkpoints(merge_env, gate_env, monkeypatch):
    """第 5 条起 429：1-4 落断点；恢复后只重跑 5-10。"""
    gate_env.value = 4
    _FakeGenerator.server_429_from_index = 5
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda: True)

    _run_merge("merge-resume", _items(10))

    checkpoint_dir = note_module._merge_checkpoint_dir("merge-resume")
    written = sorted(
        int(name.split(".")[0])
        for name in __import__("os").listdir(checkpoint_dir)
        if name.endswith(".json")
    )
    assert written == [1, 2, 3, 4], f"停放时应只保住已完成条目的断点，实际 {written}"
    assert _FakeGenerator.park_calls == ["merge-resume"], "429 必须走停放而不是失败"
    assert "merge-resume" not in merge_env, "停放不是终态，不该保存合并笔记"

    # 配额恢复后重新派发：1-4 命中断点，不再调生成。
    _FakeGenerator.generate_calls = []
    _FakeGenerator.server_429_from_index = None
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda: False)

    _run_merge("merge-resume", _items(10))

    assert sorted(_FakeGenerator.generate_calls) == list(range(5, 11)), (
        f"恢复后只应生成 5-10，实际 {sorted(_FakeGenerator.generate_calls)}"
    )
    note = merge_env["merge-resume"]
    for i in range(1, 11):
        assert f"## {i}. 视频{i}" in note.markdown, f"合并正文缺少第 {i} 条"
    assert not __import__("os").path.exists(checkpoint_dir), "终态成功后断点目录必须删除"
