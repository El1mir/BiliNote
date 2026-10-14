"""ticket 014-01：任务状态内存注册表的语义与「命中即零系统调用」。

为什么这么测：

* 注册表本身极简（约 30 行），真正要锁住的是**两条契约**：
  ① 命中时绝不能碰文件系统——这是全部收益的来源，用 ``os.stat`` 计数断言，
     不看墙钟时间（时间在 CI 上不稳定，计数是确定性的）；
  ② ``drop`` 必须真的清掉——删除 / 重试后残留旧值是这套方案最危险的失败模式。
* 计数一律用 ``os.stat``，**不用 ``open``**：``app/`` 下有 Cython 编译产物，C 实现
  绕过 ``builtins.open``，``open`` 计数会偏低。这条口径写在 conftest 的 docstring 里。
* ``BILINOTE_CACHE`` 的取值判定单独测，因为 ``disabled()`` 每次读环境变量、不做
  模块级缓存——这个取舍让测试必须用 ``monkeypatch.setenv/delenv`` 而不是重置模块状态。
"""

import os

from app.services import task_status_cache as cache


def _sample(task_id: str = "t-1") -> dict:
    return {
        "task_id": task_id,
        "status": "SUCCESS",
        "stage": "success",
        "stage_label": "已完成",
        "progress": 100,
        "stage_progress": 100,
        "message": "",
    }


def test_put_then_get_returns_same_object():
    payload = _sample()
    cache.put("t-1", payload)
    assert cache.get("t-1") is payload


def test_get_miss_returns_none():
    assert cache.get("nope") is None


def test_drop_removes_entry():
    cache.put("t-1", _sample())
    cache.drop("t-1")
    assert cache.get("t-1") is None


def test_drop_is_idempotent():
    """重复删除不能抛——删除与重试路径都可能调到。"""
    cache.drop("never-existed")
    cache.put("t-1", _sample())
    cache.drop("t-1")
    cache.drop("t-1")
    assert cache.get("t-1") is None


def test_clear_empties_everything():
    cache.put("t-1", _sample("t-1"))
    cache.put("t-2", _sample("t-2"))
    cache.clear()
    assert cache.get("t-1") is None
    assert cache.get("t-2") is None


def test_hit_performs_zero_stat_calls(monkeypatch):
    """**这是本模块存在意义的断言**：命中路径上不发生任何 stat。

    用 monkeypatch 把 ``os.stat`` 换成计数器，断言读取命中时计数为 0。若这里失败，
    说明快路径漏回了文件系统，198ms/轮的收益就不成立。
    """
    calls = {"n": 0}
    real_stat = os.stat

    def counting_stat(*args, **kwargs):
        calls["n"] += 1
        return real_stat(*args, **kwargs)

    monkeypatch.setattr(os, "stat", counting_stat)

    cache.put("t-1", _sample())
    calls["n"] = 0  # 只统计命中路径本身

    assert cache.get("t-1") is not None
    assert calls["n"] == 0, f"命中路径产生了 {calls['n']} 次 stat，快路径失效"


def test_miss_does_not_imply_stat():
    """未命中只是返回 None，本模块自身不应去碰文件系统。

    真正的文件回退发生在调用方（``_read_task_status``），那部分由 ticket 02 覆盖。
    这里只锁住「模块自身零 IO」。
    """
    assert cache.get("absent") is None


# --------------------------------------------------------------------------
# BILINOTE_CACHE 开关
# --------------------------------------------------------------------------


def test_disabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("BILINOTE_CACHE", raising=False)
    assert cache.disabled() is False


def test_get_bypasses_when_disabled(monkeypatch):
    """开关打开（关闭缓存）时，已写入的值也必须不返回。

    这是 before/after 对比测量的基础：同一个测量脚本在 ``BILINOTE_CACHE=off`` 下
    必须完整回落到文件路径，否则两组数字不可比。
    """
    cache.put("t-1", _sample())
    monkeypatch.setenv("BILINOTE_CACHE", "off")
    assert cache.disabled() is True
    assert cache.get("t-1") is None


def test_put_still_stores_when_disabled(monkeypatch):
    """关闭时 ``put`` 仍然写入，只是 ``get`` 不读。

    刻意如此：避免「关缓存」改变写入方的行为（写方还要落盘，行为应保持一致）。
    开关只影响读路径的可见性。
    """
    monkeypatch.setenv("BILINOTE_CACHE", "off")
    cache.put("t-1", _sample())
    monkeypatch.delenv("BILINOTE_CACHE", raising=False)
    assert cache.get("t-1") is not None


def test_falsy_values(monkeypatch):
    for raw in ("0", "false", "off", "no", "OFF", " False ", "No"):
        monkeypatch.setenv("BILINOTE_CACHE", raw)
        assert cache.disabled() is True, f"{raw!r} 应被视为关闭"


def test_truthy_values(monkeypatch):
    for raw in ("1", "true", "on", "yes", "anything"):
        monkeypatch.setenv("BILINOTE_CACHE", raw)
        assert cache.disabled() is False, f"{raw!r} 不应被视为关闭"


def test_conftest_fixture_cache_off(cache_off):
    """conftest 的 ``cache_off`` fixture 真的生效（防基建自身失效）。"""
    assert cache_off == "off"
    cache.put("t-1", _sample())
    assert cache.get("t-1") is None
