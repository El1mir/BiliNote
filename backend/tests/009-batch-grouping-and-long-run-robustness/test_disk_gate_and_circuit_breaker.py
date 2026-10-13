"""spec 009 ticket 04：磁盘门禁与连续失败熔断。"""

from unittest import mock

from app.routers import note as note_module
from app.routers.note import _CircuitBreaker, _check_disk_space, _human_bytes


# --------------------------------------------------------------------------
# 熔断器
# --------------------------------------------------------------------------


def test_breaker_pauses_after_threshold():
    breaker = _CircuitBreaker(threshold=3)
    assert breaker.is_paused() is False
    assert breaker.record_failure() is False  # 1
    assert breaker.record_failure() is False  # 2
    assert breaker.record_failure() is True  # 3 → 触发
    assert breaker.is_paused() is True
    # 已经暂停后再失败不再重复「触发」
    assert breaker.record_failure() is False


def test_breaker_success_resets_counter():
    breaker = _CircuitBreaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.consecutive_failures == 0
    # 归零后要再连挂 3 次才触发
    assert breaker.record_failure() is False
    assert breaker.record_failure() is False
    assert breaker.record_failure() is True


def test_breaker_threshold_zero_disables():
    breaker = _CircuitBreaker(threshold=0)
    for _ in range(50):
        assert breaker.record_failure() is False
    assert breaker.is_paused() is False


def test_breaker_configure_to_zero_clears_pause():
    """关掉熔断必须顺手解除暂停，否则任务还是不动。"""
    breaker = _CircuitBreaker(threshold=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_paused() is True
    assert breaker.configure(0) is True
    assert breaker.is_paused() is False
    assert breaker.consecutive_failures == 0


def test_breaker_reset_on_resubmit():
    """用户重新提交 = 熔断复位（spec 009 决策 12）。"""
    breaker = _CircuitBreaker(threshold=2)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_paused() is True
    breaker.reset()
    assert breaker.is_paused() is False
    assert breaker.consecutive_failures == 0


def test_breaker_is_thread_safe():
    import threading

    breaker = _CircuitBreaker(threshold=10_000)
    threads = [
        threading.Thread(target=lambda: [breaker.record_failure() for _ in range(200)])
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert breaker.consecutive_failures == 1600


def test_get_circuit_breaker_reads_threshold_from_settings():
    with mock.patch.object(
        note_module,
        "_safe_general_settings",
        return_value={"circuit_breaker_threshold": 7},
    ):
        breaker = note_module._get_circuit_breaker()
    assert breaker.threshold == 7

    with mock.patch.object(
        note_module,
        "_safe_general_settings",
        return_value={"circuit_breaker_threshold": 0},
    ):
        breaker = note_module._get_circuit_breaker()
    assert breaker.threshold == 0

    # 设置里没有这个键时回落默认 5
    with mock.patch.object(note_module, "_safe_general_settings", return_value={}):
        breaker = note_module._get_circuit_breaker()
    assert breaker.threshold == 5


# --------------------------------------------------------------------------
# 磁盘门禁
# --------------------------------------------------------------------------


def test_disk_gate_disabled_by_default():
    with mock.patch.object(note_module, "_safe_general_settings", return_value={}):
        assert _check_disk_space() is None


def test_disk_gate_allows_when_enough_space():
    fake = mock.Mock(free=100 * 1024**3)
    with (
        mock.patch.object(
            note_module,
            "_safe_general_settings",
            return_value={"min_free_disk_bytes": 5 * 1024**3},
        ),
        mock.patch("shutil.disk_usage", return_value=fake),
    ):
        assert _check_disk_space() is None


def test_disk_gate_rejects_when_low():
    fake = mock.Mock(free=1024**3)
    with (
        mock.patch.object(
            note_module,
            "_safe_general_settings",
            return_value={"min_free_disk_bytes": 5 * 1024**3},
        ),
        mock.patch("shutil.disk_usage", return_value=fake),
    ):
        message = _check_disk_space()
    assert message is not None
    assert "磁盘剩余空间不足" in message
    assert "1.0 GB" in message


def test_disk_gate_fails_open_when_settings_unreadable():
    """设置读不出来时必须放行 —— 否则数据库抖一下生成功能就锁死了。

    走真实路径：DAO 抛异常 → ``_safe_general_settings`` 吞掉返回 {} →
    ``min_free_disk_bytes`` 缺失按 0 处理 → 不拦截。
    """
    with mock.patch(
        "app.db.general_settings_dao.get_general_settings",
        side_effect=RuntimeError("db down"),
    ):
        assert _check_disk_space() is None
        # 熔断阈值读不到也要有默认值，不能因此关掉保护
        assert note_module._get_circuit_breaker().threshold == 5


def test_disk_gate_fails_open_when_disk_unreadable():
    with (
        mock.patch.object(
            note_module,
            "_safe_general_settings",
            return_value={"min_free_disk_bytes": 5 * 1024**3},
        ),
        mock.patch("shutil.disk_usage", side_effect=OSError("no such device")),
    ):
        assert _check_disk_space() is None


def test_disk_gate_tolerates_garbage_value():
    with mock.patch.object(
        note_module,
        "_safe_general_settings",
        return_value={"min_free_disk_bytes": "abc"},
    ):
        assert _check_disk_space() is None


def test_human_bytes():
    assert _human_bytes(0) == "0 B"
    assert _human_bytes(512) == "512 B"
    assert _human_bytes(1024) == "1.0 KB"
    assert _human_bytes(5 * 1024**3) == "5.0 GB"
