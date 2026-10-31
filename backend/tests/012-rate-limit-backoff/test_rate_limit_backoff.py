"""429 退避与停放（spec 012）。

用户需求（m04754）：遇到 429 就停止一段时间，每 5 分钟重试一次，最大等待一小时。

这个文件钉住五件事，每一件都对应一个会静默出错的地方：

1. **429 不是失败**。它既不消耗 ``NOTE_MAX_RETRIES`` 预算，也不计熔断 —— 否则
   5 条任务撞上配额耗尽就能把熔断打开，后面一百多条连等的机会都没有。
2. **冷却窗口是全局共享的**，而且必须在**取并发槽位之前**等 —— 放在后面的话，
   一边等冷却一边白占着信号量，别的任务连排队的资格都没有。
3. **等满上限就交还队列**（返回 :data:`RATE_LIMIT_PARKED` 哨兵），不标 FAILED。
   让 worker 线程各睡一小时会把后面一百多条全堵死，而 worker 只有 5 个。
4. **恢复循环重新派发前要清冷却**，否则第一次的 ``_first_hit_at`` 还在，任务刚
   派发出去就又被判「已等满一小时」，在停放区和队列之间原地打转。
5. **等待预算是从第一次 429 起算的**（不是最后一次）。从最后一次起算的话，持续
   429 会让窗口无限后推，「最大等一小时」永远到不了。

约定（与 009/010/011 一致）：不引入 conftest.py；断言读 body 的 ``code`` 字段。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import note as note_module
from app.utils import llm_rate_limit as rl


class _Note:
    def __init__(self, markdown):
        self.markdown = markdown


class _StubGenerator:
    """假的 NoteGenerator：只暴露 ``_execute_note_with_retry`` 用到的三样东西。

    ``rate_limited_rounds`` 控制前几轮返回 429，用来验证「429 不消耗重试预算」；
    ``plain_failure`` 则是普通失败（两个标记都不置位），用来验证「普通失败照旧消耗
    重试预算」—— 没有它的话 ``run()`` 会直接返回成功，用例根本走不到重试分支。
    """

    def __init__(self, rate_limited_rounds=0, non_retryable=False, plain_failure=False):
        self.calls = 0
        self.rate_limited_rounds = rate_limited_rounds
        self.non_retryable = non_retryable
        self.plain_failure = plain_failure
        self.last_error_rate_limited = False
        self.last_error_non_retryable = False
        self.statuses = []

    def run(self):
        """充当 ``execute_fn``。"""
        self.calls += 1
        self.last_error_rate_limited = self.calls <= self.rate_limited_rounds
        self.last_error_non_retryable = self.non_retryable
        if self.plain_failure or self.last_error_rate_limited or self.non_retryable:
            return None
        return _Note("# 笔记")

    def _update_status(self, task_id, status, message=""):
        self.statuses.append((task_id, getattr(status, "value", status), message))


@pytest.fixture(autouse=True)
def _clean_cooldown():
    """每个用例前后都清空冷却窗口。

    这不是洁癖：``_RATE_LIMIT_COOLDOWN`` 是模块级单例，上一个用例留下的窗口会让
    下一个用例的 ``provider_slot`` 真的睡过去（默认 300 s）。
    """
    rl.reset_rate_limit()
    yield
    rl.reset_rate_limit()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """一个只挂了 note 路由的 app；返回 (client, results_dir)。"""
    results_dir = tmp_path / "note_results"
    results_dir.mkdir()
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(results_dir))

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app), results_dir


# ---------------------------------------------------------------------------
# 429 判定
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Error code: 429 - {'error': {'code': '429', 'message': 'quota exhausted'}}",
        "请求过于频繁（HTTP 429）：检查配额或稍后重试",
        "rate limit reached for requests",
        "Too Many Requests",
        "You exceeded your current quota",
    ],
)
def test_rate_limit_text_is_recognised(text):
    """底层异常常被翻成 RuntimeError、属性全丢，所以文案判定不能省。"""
    assert rl.is_rate_limit_error(RuntimeError(text)) is True


@pytest.mark.parametrize(
    "text",
    [
        "Invalid API key",
        "The model `gpt-x` does not exist",
        "read timed out",
        "磁盘剩余空间不足",
    ],
)
def test_non_rate_limit_text_is_not_recognised(text):
    assert rl.is_rate_limit_error(RuntimeError(text)) is False


def test_rate_limit_status_code_and_attribute_are_recognised():
    class WithStatus(Exception):
        status_code = 429

    class WithFlag(Exception):
        rate_limited = True

    assert rl.is_rate_limit_error(WithStatus("whatever")) is True
    assert rl.is_rate_limit_error(WithFlag("whatever")) is True


def _pin_cooldown(monkeypatch, cooldown=None, max_wait=None):
    """钉住 429 冷却的两个时长。

    这两个值现在是「设置 → 通用」里的可配置项，``note_rate_limit_hit()`` 在未显式
    传参时通过 :mod:`app.services.runtime_limits` 读取。以前这些用例直接改
    ``rl.RATE_LIMIT_COOLDOWN_SECONDS``；那个模块常量如今只是「读不到配置时的兜底」，
    改它不会再影响执行路径 —— 所以要钉在真正被读的那一层。
    """
    from app.services import runtime_limits

    if cooldown is not None:
        monkeypatch.setattr(
            runtime_limits, "llm_rate_limit_cooldown_seconds", lambda: cooldown
        )
    if max_wait is not None:
        monkeypatch.setattr(
            runtime_limits, "llm_rate_limit_max_wait_seconds", lambda: max_wait
        )


# ---------------------------------------------------------------------------
# 冷却窗口
# ---------------------------------------------------------------------------


def test_hit_extends_window_and_budget_counts_from_first_hit(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])
    _pin_cooldown(monkeypatch, cooldown=300.0, max_wait=600.0)

    assert rl.note_rate_limit_hit() is False
    clock["now"] += 100.0
    # 只过了 100s，远未满 600s
    assert rl.note_rate_limit_hit() is False
    assert rl.rate_limit_waited_seconds() == pytest.approx(100.0)
    # 窗口被后推到 now+300 = 1400；若沿用第一次的窗口这里会是 200
    assert rl.rate_limit_remaining() == pytest.approx(300.0)

    # 距**第一次** 429 已 600s → 预算用满
    clock["now"] += 500.0
    assert rl.note_rate_limit_hit() is True


def test_max_wait_zero_means_never_give_up(monkeypatch):
    """``max_wait_seconds=0`` 是「不设上限」，不是「立刻放弃」。"""
    clock = {"now": 0.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])
    _pin_cooldown(monkeypatch, cooldown=10.0, max_wait=0.0)

    assert rl.note_rate_limit_hit() is False
    clock["now"] += 100000.0
    assert rl.note_rate_limit_hit() is False


def test_clear_resets_window_and_budget(monkeypatch):
    _pin_cooldown(monkeypatch, cooldown=600.0, max_wait=60.0)
    rl.note_rate_limit_hit()
    assert rl.rate_limit_remaining() > 0

    rl.clear_rate_limit()

    assert rl.rate_limit_remaining() == 0.0
    assert rl.rate_limit_waited_seconds() == 0.0
    # 清完之后预算也是新的：立刻再撞一次不会直接判「已等满」
    assert rl.note_rate_limit_hit() is False


def test_wait_returns_immediately_without_cooldown():
    assert rl.wait_for_rate_limit() == 0.0


def test_wait_sleeps_in_chunks_until_window_closes(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(rl.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        rl.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    _pin_cooldown(monkeypatch, cooldown=10.0)

    rl.note_rate_limit_hit()

    assert rl.wait_for_rate_limit(chunk_seconds=1.0) == pytest.approx(10.0)
    assert rl.rate_limit_remaining() == 0.0


def test_reset_limiters_clears_cooldown(monkeypatch):
    """``reset_limiters()`` 是测试隔离入口，漏清冷却会让后续用例凭空睡 5 分钟。"""
    _pin_cooldown(monkeypatch, cooldown=600.0)
    rl.note_rate_limit_hit()
    assert rl.rate_limit_remaining() > 0

    rl.reset_limiters()

    assert rl.rate_limit_remaining() == 0.0


def test_provider_slot_waits_for_cooldown_before_acquiring(monkeypatch):
    """等冷却必须在取并发槽位**之前**。

    放在后面（``with limiter.slot(): wait_for_rate_limit()``）的话，每个在途任务
    都会一边等冷却一边白占着一个信号量，并发额度被白白锁死。
    """
    rl.reset_limiters()
    waits = []

    def fake_wait():
        waits.append(1)
        return 0.0

    monkeypatch.setattr(rl, "wait_for_rate_limit", fake_wait)

    with rl.provider_slot("test-provider-cooldown"):
        assert waits == [1]


# ---------------------------------------------------------------------------
# 任务级退避
# ---------------------------------------------------------------------------


@pytest.fixture
def _fast_retry(monkeypatch):
    """让普通重试分支不真的睡 5+15+45 秒。"""
    monkeypatch.setattr(rl.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(note_module.time, "sleep", lambda seconds: None)


def test_rate_limited_does_not_consume_retry_budget(monkeypatch, _fast_retry):
    """连撞 2 次 429 后成功 —— 2 次退避不能吃掉 NOTE_MAX_RETRIES 的额度。"""
    generator = _StubGenerator(rate_limited_rounds=2)
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda *a, **k: False)
    monkeypatch.setattr(note_module, "wait_for_rate_limit", lambda *a, **k: 0.0)
    monkeypatch.setattr(note_module, "clear_rate_limit", lambda: None)

    note = note_module._execute_note_with_retry("t1", generator, generator.run)

    assert note is not None
    assert getattr(note, "markdown", None)
    assert generator.calls == 3
    # 退避期间任务必须显示「还在等」，而不是失败
    assert generator.statuses
    for _task_id, status, message in generator.statuses:
        assert status == "PENDING"
        assert message == "供应商限流，等待配额恢复"


def test_rate_limited_waiting_does_not_touch_circuit_breaker(monkeypatch, _fast_retry):
    """429 退避期间不能计熔断：否则 5 条任务就能把后面全部挡死。"""
    generator = _StubGenerator(rate_limited_rounds=10)
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda *a, **k: False)
    monkeypatch.setattr(note_module, "wait_for_rate_limit", lambda *a, **k: 0.0)
    monkeypatch.setattr(note_module, "clear_rate_limit", lambda: None)

    breaker = note_module._CircuitBreaker(threshold=5)
    monkeypatch.setattr(note_module, "_CIRCUIT_BREAKER", breaker)

    note = note_module._execute_note_with_retry("t1", generator, generator.run)

    assert note is not None
    assert getattr(note, "markdown", None)
    assert generator.calls == 11
    assert breaker.consecutive_failures == 0
    assert breaker.is_paused() is False


def test_budget_exhausted_returns_parked_sentinel(monkeypatch, _fast_retry):
    generator = _StubGenerator(rate_limited_rounds=1)
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda *a, **k: True)

    note = note_module._execute_note_with_retry("t1", generator, generator.run)

    assert note == note_module.RATE_LIMIT_PARKED
    # 哨兵不是 None：None 会被调用方计熔断并标 FAILED
    assert note is not None


def test_success_clears_cooldown(monkeypatch, _fast_retry):
    cleared = []
    generator = _StubGenerator(rate_limited_rounds=1)
    monkeypatch.setattr(note_module, "note_rate_limit_hit", lambda *a, **k: False)
    monkeypatch.setattr(note_module, "wait_for_rate_limit", lambda *a, **k: 0.0)
    monkeypatch.setattr(note_module, "clear_rate_limit", lambda: cleared.append(1))

    note_module._execute_note_with_retry("t1", generator, generator.run)

    assert cleared == [1]


def test_non_retryable_still_stops_immediately(monkeypatch, _fast_retry):
    generator = _StubGenerator(non_retryable=True)

    note = note_module._execute_note_with_retry("t1", generator, generator.run)

    assert note is None
    assert generator.calls == 1


def test_plain_failure_still_uses_retry_budget(monkeypatch, _fast_retry):
    generator = _StubGenerator(plain_failure=True)

    note = note_module._execute_note_with_retry("t1", generator, generator.run)

    assert note is None
    # 首次 + NOTE_MAX_RETRIES 次重试
    assert generator.calls == note_module.NOTE_MAX_RETRIES + 1


# ---------------------------------------------------------------------------
# 停放区与恢复循环
# ---------------------------------------------------------------------------


@pytest.fixture
def _parking(monkeypatch):
    """把停放区用到的外部依赖都换掉，避免真写文件 / 真起恢复线程。"""
    written = []
    dispatched = []
    monkeypatch.setattr(note_module, "_PARKED_TASKS", {})
    monkeypatch.setattr(
        note_module,
        "_ensure_rate_limit_resume_loop",
        lambda: written.append(("loop-started",)),
    )
    monkeypatch.setattr(
        note_module, "_dispatch_note_task", lambda kwargs: dispatched.append(kwargs)
    )

    class _StubNoteGenerator:
        def _update_status(self, task_id, status, message=""):
            written.append((task_id, getattr(status, "value", status), message))

    monkeypatch.setattr(note_module, "NoteGenerator", _StubNoteGenerator)
    return written, dispatched


def test_park_writes_pending_not_failed(_parking):
    written, _dispatched = _parking

    note_module._park_rate_limited_task("t1", {"task_id": "t1"})

    assert ("t1", "PENDING", "供应商配额受限，等待自动恢复") in written
    assert note_module.parked_task_ids() == ["t1"]


def test_resume_waits_while_cooldown_remains(monkeypatch, _parking):
    _written, dispatched = _parking
    monkeypatch.setattr(note_module, "rate_limit_remaining", lambda: 120.0)
    note_module._park_rate_limited_task("t1", {"task_id": "t1"})

    assert note_module._resume_parked_tasks() == 0
    assert dispatched == []
    assert note_module.parked_task_ids() == ["t1"]


def test_resume_dispatches_and_clears_cooldown(monkeypatch, _parking):
    _written, dispatched = _parking
    cleared = []
    monkeypatch.setattr(note_module, "rate_limit_remaining", lambda: 0.0)
    monkeypatch.setattr(note_module, "clear_rate_limit", lambda: cleared.append(1))
    note_module._park_rate_limited_task("t1", {"task_id": "t1"})
    note_module._park_rate_limited_task("t2", {"task_id": "t2"})

    assert note_module._resume_parked_tasks() == 2

    assert sorted(item["task_id"] for item in dispatched) == ["t1", "t2"]
    assert note_module.parked_task_ids() == []
    # 不清冷却的话，重新派发出去的任务会立刻又被判「已等满一小时」
    assert cleared == [1]


def test_resume_with_empty_parking_is_noop(monkeypatch, _parking):
    _written, dispatched = _parking
    monkeypatch.setattr(note_module, "rate_limit_remaining", lambda: 0.0)

    assert note_module._resume_parked_tasks() == 0
    assert dispatched == []


# ---------------------------------------------------------------------------
# 路由契约
# ---------------------------------------------------------------------------


def test_rate_limit_defaults_match_the_requirement(monkeypatch):
    """需求原文：每 5 分钟重试一次，最大等待一小时。"""
    monkeypatch.delenv("RATE_LIMIT_COOLDOWN_SECONDS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_MAX_WAIT_SECONDS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_RESUME_INTERVAL_SECONDS", raising=False)
    import importlib

    reloaded = importlib.reload(rl)
    try:
        assert reloaded.RATE_LIMIT_COOLDOWN_SECONDS == 300.0
        assert reloaded.RATE_LIMIT_MAX_WAIT_SECONDS == 3600.0
        assert reloaded.RATE_LIMIT_RESUME_INTERVAL_SECONDS == 300.0
    finally:
        # 把模块恢复成原来的状态，免得影响后续用例
        importlib.reload(rl)


def test_router_exposes_the_parking_api(env):
    """路由模块必须能拿到停放区的观测入口（运维/测试都靠它）。"""
    _client, _results_dir = env
    assert callable(note_module.parked_task_ids)
    assert isinstance(note_module.RATE_LIMIT_PARKED, str)
    assert note_module.RATE_LIMIT_PARKED
