"""spec 022 W1：合并任务内部扇出（D2）。

10 条子项、闸门 4：同时生成的最大条数必须是 4（不是串行），且最终章节顺序
严格等于用户勾选顺序 1..10。
"""

import threading
import time
from types import SimpleNamespace

import pytest

from app.routers import note as note_module


class _Limit:
    def __init__(self, value):
        self.value = value


@pytest.fixture
def gate_env(monkeypatch):
    holder = _Limit(4)
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    monkeypatch.setattr(note_module, "_safe_max_parallel_notes", lambda: holder.value)
    yield holder
    gate = note_module._PARALLEL_GATE
    if gate is not None:
        assert gate.active == 0, f"用例结束时闸门仍有 {gate.active} 个名额未归还"


class _Probe:
    def __init__(self):
        self.lock = threading.Lock()
        self.current = 0
        self.max_seen = 0

    def enter(self):
        with self.lock:
            self.current += 1
            self.max_seen = max(self.max_seen, self.current)

    def leave(self):
        with self.lock:
            self.current -= 1


class _FakeGenerator:
    """NoteGenerator 的替身：只提供 _update_status 与 generate。"""

    def __init__(self, probe=None):
        self._probe = probe

    def _update_status(self, *args, **kwargs):
        return None

    def generate(self, **kwargs):
        url = kwargs["video_url"]
        if self._probe is not None:
            self._probe.enter()
            time.sleep(0.05)
            self._probe.leave()
        return SimpleNamespace(
            markdown=f"### {url}",
            transcript=None,
            audio_meta=SimpleNamespace(
                title=url, duration=1.0, video_id=url.rsplit("/", 1)[-1], cover_url=None
            ),
        )


def _items(count):
    return [{"url": f"https://video/{i}", "title": f"标题{i}"} for i in range(1, count + 1)]


def _kwargs(tmp_path, items, gate=4):
    return dict(
        task_id="w1-merge",
        items=items,
        merge_title="合并",
        merge_polish=False,
        model_name=None,
        provider_id=None,
        platform="bilibili",
        quality=None,
        link=False,
        screenshot=False,
        _format=None,
        scene=None,
        detail=None,
        extras=None,
        video_understanding=False,
        video_interval=None,
        grid_size=None,
        sampling_mode="interval",
        max_frames=None,
        frames_per_second=None,
        frame_limit_mode="count",
        ocr_assist=None,
        park_kwargs={},
    )


@pytest.fixture
def merge_env(tmp_path, monkeypatch, gate_env):
    probe = _Probe()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(tmp_path / "notes"))
    monkeypatch.setattr(note_module, "NoteGenerator", lambda: _FakeGenerator(probe))
    monkeypatch.setattr(note_module, "_cleanup_merged_subtask_files", lambda _id: None)
    monkeypatch.setattr(note_module, "_enforce_cache_limit_in_background", lambda: None)
    monkeypatch.setattr(note_module, "_park_rate_limited_task", lambda *_a, **_k: None)
    saved = {}
    monkeypatch.setattr(
        note_module, "save_note_to_file", lambda task_id, note: saved.setdefault(task_id, note)
    )
    frozen_breaker = SimpleNamespace(
        record_success=lambda: None, record_failure=lambda *_a, **_k: None
    )
    monkeypatch.setattr(note_module, "_get_circuit_breaker", lambda: frozen_breaker)

    def fake_retry(sub_task_id, generator, execute_fn):
        return execute_fn()

    monkeypatch.setattr(note_module, "_execute_note_with_retry", fake_retry)
    return SimpleNamespace(probe=probe, saved=saved)


def test_merge_fans_out_four_and_keeps_order(merge_env, gate_env):
    items = _items(10)
    note_module._run_merged_note_task(**_kwargs(".", items, gate=4))

    assert merge_env.probe.max_seen == 4, f"扇出峰值应为 4，实际 {merge_env.probe.max_seen}"
    merged = merge_env.saved["w1-merge"]
    positions = [merged.markdown.index(f"https://video/{i}") for i in range(1, 11)]
    assert positions == sorted(positions), "章节顺序必须等于输入顺序 1..10"
