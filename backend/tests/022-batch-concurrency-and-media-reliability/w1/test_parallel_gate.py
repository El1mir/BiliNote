"""spec 022 W1：闸门是唯一并发上限（D1）。

以前 _run_with_parallel_gate 先拿名额再把任务体交给 task_serial_executor
（固定 5 worker），用户设 8 时实际并发只有 5。本用例直接测「设置 8 → 10 个假任务
峰值 8；设置 3 → 峰值 3」，即用户设置就是实际在途上限。
"""

import threading
import time

import pytest

from app.routers import note as note_module


class _Limit:
    def __init__(self, value):
        self.value = value


@pytest.fixture
def gate_env(monkeypatch):
    holder = _Limit(2)
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    monkeypatch.setattr(note_module, "_safe_max_parallel_notes", lambda: holder.value)
    yield holder
    gate = note_module._PARALLEL_GATE
    if gate is not None:
        assert gate.active == 0, f"用例结束时闸门仍有 {gate.active} 个名额未归还"


class _Probe:
    """记录同时进入任务体的线程数与总进入次数。"""

    def __init__(self, target, delay=0.03):
        self._lock = threading.Lock()
        self._target = target
        self._delay = delay
        self.current = 0
        self.max_seen = 0
        self.entered = 0
        self.done = threading.Event()

    def body(self):
        with self._lock:
            self.current += 1
            self.entered += 1
            self.max_seen = max(self.max_seen, self.current)
            last = self.entered >= self._target
        try:
            time.sleep(self._delay)
        finally:
            with self._lock:
                self.current -= 1
            if last:
                self.done.set()


def _run_batch(monkeypatch, count):
    probe = _Probe(count)

    def fake_run_note_task(**kwargs):
        note_module._run_with_parallel_gate(probe.body)

    monkeypatch.setattr(note_module, "run_note_task", fake_run_note_task)
    for index in range(count):
        note_module._dispatch_note_task({"task_id": f"w1-t{index}"})
    assert probe.done.wait(20.0), f"{count} 条任务在 20s 内没跑完"
    return probe


def test_setting_8_means_peak_8(gate_env, monkeypatch):
    gate_env.value = 8
    probe = _run_batch(monkeypatch, count=10)

    assert probe.entered == 10
    assert probe.max_seen == 8, f"设置 8 时最大在途应为 8，实际 {probe.max_seen}"


def test_setting_3_means_peak_3(gate_env, monkeypatch):
    gate_env.value = 3
    probe = _run_batch(monkeypatch, count=10)

    assert probe.entered == 10
    assert probe.max_seen == 3, f"设置 3 时最大在途应为 3，实际 {probe.max_seen}"
