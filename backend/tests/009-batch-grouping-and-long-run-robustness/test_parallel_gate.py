"""spec 009 ticket 02：并行闸门的扩缩容与真并发。

早期实现用 ``threading.BoundedSemaphore``，扩容时直接换了一个新对象 —— 已经阻塞在
旧信号量上的线程永远等不到 release。这里把这几个场景钉死。
"""

import threading
import time

from app.routers.note import _ParallelGate


def test_gate_limits_concurrency():
    gate = _ParallelGate(2)
    seen = []
    lock = threading.Lock()

    def worker():
        with gate:
            with lock:
                seen.append(gate.active)
            time.sleep(0.05)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max(seen) <= 2
    assert gate.active == 0


def test_reconfigure_up_wakes_blocked_threads():
    """扩容必须唤醒**已经在等**的线程（旧实现的换对象 bug 就在这里）。"""
    gate = _ParallelGate(1)
    started = threading.Event()
    finished = threading.Event()

    def holder():
        with gate:
            started.set()
            time.sleep(0.4)

    def waiter():
        started.wait(timeout=2)
        with gate:
            finished.set()

    t1 = threading.Thread(target=holder)
    t2 = threading.Thread(target=waiter)
    t1.start()
    t2.start()
    started.wait(timeout=2)

    # 此刻 waiter 已经阻塞在旧额度上；扩容到 2 应该立刻放它过去。
    assert gate.reconfigure(2) is True
    assert finished.wait(timeout=2) is True, "扩容没有唤醒已阻塞的线程"

    t1.join()
    t2.join()
    assert gate.active == 0


def test_reconfigure_down_does_not_kill_running_task():
    """缩容只影响后续进入的任务，不打断已在跑的任务。"""
    gate = _ParallelGate(2)
    entered = threading.Event()
    release = threading.Event()

    def worker():
        with gate:
            entered.set()
            release.wait(timeout=2)

    t = threading.Thread(target=worker)
    t.start()
    entered.wait(timeout=2)

    assert gate.reconfigure(1) is True
    assert gate.limit == 1
    assert gate.active == 1  # 还在跑，没被打断

    release.set()
    t.join()
    assert gate.active == 0


def test_reconfigure_same_value_returns_false():
    gate = _ParallelGate(3)
    assert gate.reconfigure(3) is False
    assert gate.reconfigure(2) is True
    assert gate.reconfigure(2) is False


def test_acquire_timeout_returns_false_when_full():
    gate = _ParallelGate(1)
    assert gate.acquire() is True
    assert gate.acquire(timeout=0.05) is False
    gate.release()
    assert gate.acquire(timeout=0.5) is True


def test_release_is_idempotent():
    """多 release 不能把计数打成负数（BoundedSemaphore 会在这里 ValueError）。"""
    gate = _ParallelGate(1)
    gate.release()
    gate.release()
    assert gate.active == 0


def test_limit_is_at_least_one():
    assert _ParallelGate(0).limit == 1
    assert _ParallelGate(-5).limit == 1
