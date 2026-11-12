"""spec 009 ticket 02：分发池 + 并行闸门合起来的真并发行为。

**分层事实（读源码确认，测试按这个分层写）**：

1. ``note.py:_dispatch_note_task`` 只是 ``_get_dispatch_pool().submit(run_note_task, **kw)``
   —— 分发池（``MAX_PARALLEL_NOTES_LIMIT`` = 8 个 worker）**本身不限流**，
   它的作用是让 200 条任务「一起进池排队」，而不是 200 个线程。
2. 真正限流的是 ``_ParallelGate``，它在 ``run_note_task`` 内部经
   ``_execute_note_with_retry → _run_with_parallel_gate`` 获取。
   所以假任务体必须**显式调用** ``note_module._run_with_parallel_gate(...)``，
   否则测出来的并发只受池子大小约束，等于没测闸门。
3. 端到端观察到的并发 = ``min(闸门 limit, 分发池 8)`` —— spec 022 D1 删掉了
   ``task_serial_executor`` 那层固定 5 线程的池，闸门是唯一上限。

⚠️ ticket 02 改动点 1 写的是「先在**池外** ``gate.acquire()`` 再提交线程池」，
但实现里 ``_dispatch_note_task`` 完全没碰闸门 —— 任务**已经占住分发池 worker
之后**才在 ``_run_with_parallel_gate`` 里等门闩。闸门「在池外」这条约束成立的
只是 ``_run_with_parallel_gate`` 内部那一层（gate 在任务体外面）。这里按
**真实实现**断言，不去迁就工单描述。

``_PARALLEL_GATE`` 是模块级单例，跨用例泄漏状态，所以 fixture 每个用例前后都
把它置回 None；``_safe_max_parallel_notes`` 被替换成读一个可变的 holder，
用来模拟「用户在设置里改并行数」。
"""

import threading
import time

import pytest

from app.db.models.general_settings import MAX_PARALLEL_NOTES_LIMIT
from app.routers import note as note_module


class _Limit:
    """可变的并行上限，替代 ``_safe_max_parallel_notes()`` 的返回值。"""

    def __init__(self, value):
        self.value = value


@pytest.fixture
def gate_env(monkeypatch):
    """每个用例一张干净的闸门 + 可控的并行上限。"""
    holder = _Limit(2)
    monkeypatch.setattr(note_module, "_PARALLEL_GATE", None)
    monkeypatch.setattr(note_module, "_safe_max_parallel_notes", lambda: holder.value)
    yield holder
    # 用例跑完后闸门必须归零，否则会污染同进程里的其它用例。
    gate = note_module._PARALLEL_GATE
    if gate is not None:
        assert gate.active == 0, f"用例结束时闸门仍有 {gate.active} 个名额未归还"


class _Probe:
    """记录「同时进入任务体」的线程数、进入总次数与用到的线程名。"""

    def __init__(self, target, delay=0.02):
        self._lock = threading.Lock()
        self._target = target
        self._delay = delay
        self.current = 0
        self.max_seen = 0
        self.entered = 0
        self.thread_names = set()
        self.done = threading.Event()

    def body(self):
        with self._lock:
            self.current += 1
            self.entered += 1
            self.max_seen = max(self.max_seen, self.current)
            self.thread_names.add(threading.current_thread().name)
            last = self.entered >= self._target
        try:
            time.sleep(self._delay)
        finally:
            with self._lock:
                self.current -= 1
            if last:
                self.done.set()


def _install_fake_task(monkeypatch, probe):
    """假任务体：走真实的 ``_run_with_parallel_gate``，但不下载/不转写。"""

    def fake_run_note_task(**kwargs):
        note_module._run_with_parallel_gate(probe.body)

    monkeypatch.setattr(note_module, "run_note_task", fake_run_note_task)


def _run_batch(monkeypatch, count, delay=0.02, timeout=20.0):
    probe = _Probe(count, delay=delay)
    _install_fake_task(monkeypatch, probe)
    for index in range(count):
        note_module._dispatch_note_task({"task_id": f"t{index}"})
    assert probe.done.wait(timeout), f"{count} 条任务在 {timeout}s 内没跑完"
    return probe


def test_batch_runs_concurrently_but_within_the_gate_limit(gate_env, monkeypatch):
    """批内并发必须 > 1（不是串行）且 ≤ max_parallel_notes —— 本次修复的核心。"""
    gate_env.value = 3
    probe = _run_batch(monkeypatch, count=12, delay=0.03)

    assert probe.entered == 12, "12 条都该被分发池接收并执行"
    assert (
        probe.max_seen > 1
    ), "批量入口不该再退化成串行（Starlette BackgroundTasks 的老问题）"
    assert probe.max_seen <= 3, f"同时执行数 {probe.max_seen} 超过了并行上限 3"


def test_dispatch_pool_itself_is_a_small_bounded_container(gate_env, monkeypatch):
    """分发池不限流但必须是小的固定容量：200 条不等于 200 个线程。"""
    gate_env.value = 1  # 把闸门压到最紧，观察池子本身的规模
    probe = _run_batch(monkeypatch, count=16, delay=0.01)

    pool = note_module._get_dispatch_pool()
    assert pool._max_workers <= MAX_PARALLEL_NOTES_LIMIT
    # 闸门 limit=1 时任务体只能一个接一个地进 —— 同时刻最多 1 个。
    assert probe.max_seen == 1
    # spec 022 D1 之后闸门里直接执行任务体，不再有内层线程池轮换：
    # 用到的线程名只会来自分发池，必须被池大小卡住，而不是按任务数增长。
    assert len(probe.thread_names) <= MAX_PARALLEL_NOTES_LIMIT


def test_gate_limit_hot_update_takes_effect_without_restart(gate_env, monkeypatch):
    """运行期改并行数立即生效：同一把闸门、不同并发，不需要重启后端。"""
    gate_env.value = 3
    before = note_module._get_parallel_gate()
    wide = _run_batch(monkeypatch, count=9, delay=0.03)
    assert wide.max_seen > 1

    # 「用户在设置里调小」：只改 holder，不重建闸门。
    gate_env.value = 1
    after = note_module._get_parallel_gate()
    assert (
        after is before
    ), "热更新必须复用同一把闸门，不能换对象（换对象会遗弃阻塞线程）"
    assert after.limit == 1

    narrow = _run_batch(monkeypatch, count=6, delay=0.02)
    assert narrow.max_seen == 1, "调小后新任务必须按新上限串行"

    # 再调大：被压住的并发要能立刻恢复（缩容不能永久吞掉名额）。
    gate_env.value = 3
    again = _run_batch(monkeypatch, count=9, delay=0.03)
    assert note_module._get_parallel_gate() is before
    assert again.max_seen > 1, "扩容后并发必须恢复"
    assert again.max_seen <= 3


def test_long_batch_smoke_200_items(gate_env, monkeypatch):
    """长批量冒烟：200 条全程假任务，不爆线程、不超上限、10 秒内跑完。"""
    gate_env.value = 3
    baseline_threads = threading.active_count()
    started = time.monotonic()

    probe = _run_batch(monkeypatch, count=200, delay=0.005, timeout=10.0)

    elapsed = time.monotonic() - started
    assert probe.entered == 200, "200 条必须全部被分发池接收"
    assert probe.max_seen > 1, "200 条不能退化成串行"
    assert probe.max_seen <= 3, f"同时执行数 {probe.max_seen} 超过上限 3"
    assert elapsed < 10.0, f"200 条冒烟耗时 {elapsed:.2f}s，超出 10s 预算"

    # 不爆线程：池子是固定小容量，200 条复用同一批 worker。
    pool = note_module._get_dispatch_pool()
    assert pool._max_workers <= MAX_PARALLEL_NOTES_LIMIT
    assert (
        len(probe.thread_names) <= MAX_PARALLEL_NOTES_LIMIT + 5
    ), f"200 条任务用到了 {len(probe.thread_names)} 个不同线程，说明在按任务数造线程"

    # 全部跑完后线程数要回落到接近提交前的水位（给分发池的常驻余量）。
    for _ in range(50):
        if threading.active_count() <= baseline_threads + 20:
            break
        time.sleep(0.05)
    assert (
        threading.active_count() <= baseline_threads + 20
    ), f"线程数未回落：提交前 {baseline_threads}，现在 {threading.active_count()}"
