"""ticket 05：``/transcriber_models_status`` 的模型目录扫描缓存。

验收口径（见 ``specs/014-backend-cache-optimization/tickets/05-readonly-endpoint-ttl.md``）：
TTL 窗口内第二次请求的 ``stat`` 计数从基线 **86.0** 降到 ≈0；下载触发后第一次请求必须
反映「下载中」；TTL 过期后重新扫描；响应字段结构不变。

**本 ticket 的一处设计偏离**（已在 ticket Comments 论证）：缓存只包住**目录扫描**，
不包住**下载状态**。ticket 原文说「模块级 ``(timestamp, value)`` 单槽缓存」并把「下载
触发时显式失效」列为必需 —— 那隐含了「整个响应进缓存」。实施时发现 ``dl_state`` 本来
就是进程内内存态、每次直读零成本，把它一起缓存只会让「下载中 / 已完成」晚一个周期才
可见。所以：

* 扫描结果进缓存 → 命中时 ``stat`` 归零（主验收达成）；
* 下载状态不进缓存 → 「下载中」永远实时（该条验收达成，且不需要在触发时失效）；
* 失效挂在**下载流程收尾**（``finally``，成功失败都走），因为那才是磁盘真值变化的时刻。

时间推进用 ``monkeypatch`` 改小 ``_MODELS_STATUS_TTL_SECONDS`` + 真 ``time.sleep``（毫秒级，
不会拖慢套件）。**没有用假时钟**：缓存读的是 ``time.monotonic()``，全局打补丁会波及别的
模块，得不偿失。
"""
import json
import os
import platform
import sys
import time
import types

import pytest


@pytest.fixture
def config_module():
    from app.routers import config

    return config


@pytest.fixture
def models_registry(monkeypatch):
    """把「可见模型」固定成 3 个已知名字，避免注册表自己去读盘。"""
    from app.transcriber import whisper_models

    class _Registry:
        def __init__(self, names):
            self._names = names

        def visible_model_names(self):
            return list(self._names)

    registry = _Registry(["tiny", "base", "small"])
    monkeypatch.setattr(whisper_models, "get_registry", lambda: registry)
    return registry


@pytest.fixture
def scans(monkeypatch, config_module):
    """统计目录扫描次数（= ``_check_whisper_model_exists`` 被调了几次）。

    同时可以强制扫描结果：``scans.result = False`` 让「所有模型都还没下载」这个前提
    变确定 —— 否则用例会随**这台机器上真的有没有下过模型**而飘。
    """
    real = config_module._check_whisper_model_exists
    state = types.SimpleNamespace(calls=0, result=None)

    def fake(model_size, subdir="whisper"):
        state.calls += 1
        if state.result is not None:
            return state.result
        return real(model_size, subdir)

    def reset():
        state.calls = 0

    state.reset = reset
    monkeypatch.setattr(config_module, "_check_whisper_model_exists", fake)
    return state


@pytest.fixture
def fake_huggingface(monkeypatch):
    """替掉 ``huggingface_hub``：下载函数在**函数体内** import 它。"""
    module = types.ModuleType("huggingface_hub")
    module.calls = []  # type: ignore[attr-defined]

    def snapshot_download(*args, **kwargs):
        module.calls.append((args, kwargs))  # type: ignore[attr-defined]
        return None

    module.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return module


def _body(response):
    return json.loads(response.body)["data"]


def _row(body, model_size):
    for row in body["whisper"]:
        if row["model_size"] == model_size:
            return row
    raise AssertionError(f"响应里没有 {model_size}：{body['whisper']}")


# --- 缓存本身 ---------------------------------------------------------------


def test_first_request_scans_every_visible_model(config_module, models_registry, scans):
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


def test_second_request_within_ttl_does_not_rescan(config_module, models_registry, scans):
    config_module.get_transcriber_models_status()
    scans.reset()
    config_module.get_transcriber_models_status()
    assert scans.calls == 0


def test_cache_hit_performs_zero_stat_calls(config_module, models_registry, counter, monkeypatch):
    """主验收：命中缓存后一整轮请求的 ``os.stat`` 调用为 0。"""
    config_module.get_transcriber_models_status()
    monkeypatch.setattr(os, "stat", counter.of(os.stat))
    config_module.get_transcriber_models_status()
    assert counter.calls == 0


def test_ttl_expiry_rescans(config_module, models_registry, scans, monkeypatch):
    monkeypatch.setattr(config_module, "_MODELS_STATUS_TTL_SECONDS", 0.05)
    config_module.get_transcriber_models_status()
    scans.reset()
    time.sleep(0.08)
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


def test_reads_do_not_extend_the_ttl(config_module, models_registry, scans, monkeypatch):
    """TTL 从**上次扫描**算起：连续命中不会把它无限延长。"""
    monkeypatch.setattr(config_module, "_MODELS_STATUS_TTL_SECONDS", 0.15)
    config_module.get_transcriber_models_status()
    scans.reset()
    time.sleep(0.08)
    config_module.get_transcriber_models_status()
    assert scans.calls == 0
    time.sleep(0.10)  # 距首次扫描 0.18s > 0.15s
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


def test_cache_off_always_rescans(config_module, models_registry, scans, cache_off):
    config_module.get_transcriber_models_status()
    assert scans.calls == 3
    scans.reset()
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


# --- 失效：下载收尾 ---------------------------------------------------------


def test_download_completion_invalidates_the_scan_cache(
    config_module, models_registry, scans, fake_huggingface
):
    scans.result = False
    config_module.get_transcriber_models_status()
    config_module._do_download_whisper("tiny")
    scans.reset()
    config_module.get_transcriber_models_status()
    assert scans.calls == 3, "下载完成后仍走旧槽，新下载的模型要等 TTL 才可见"


def test_download_failure_also_invalidates_the_scan_cache(
    config_module, models_registry, scans, fake_huggingface, monkeypatch
):
    scans.result = False

    def boom(*args, **kwargs):
        raise OSError("连不上 Hub")

    monkeypatch.setattr(fake_huggingface, "snapshot_download", boom)
    config_module.get_transcriber_models_status()
    config_module._do_download_whisper("tiny")
    scans.reset()
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


def test_download_that_finds_the_model_already_present_still_invalidates(
    config_module, models_registry, scans, fake_huggingface
):
    """「已经下好、不重复下」是早退分支，``finally`` 同样要跑到。"""
    scans.result = True
    config_module.get_transcriber_models_status()
    config_module._do_download_whisper("tiny")
    assert fake_huggingface.calls == [], "已经下好的模型不该再发起下载"
    scans.reset()
    config_module.get_transcriber_models_status()
    assert scans.calls == 3


# --- 下载状态不被缓存 -------------------------------------------------------


def test_downloading_state_is_never_cached(config_module, models_registry):
    """「下载中」必须实时可见：它不在缓存里，所以别等 TTL。"""
    from app.transcriber import model_download_state as dl_state

    dl_state.mark_downloading("tiny")
    row = _row(_body(config_module.get_transcriber_models_status()), "tiny")
    assert row["downloading"] is True

    dl_state.mark_done("tiny")
    row = _row(_body(config_module.get_transcriber_models_status()), "tiny")
    assert row["downloading"] is False, "旧槽把「已下载完成」挡住了"


def test_failed_state_is_visible_without_waiting_for_ttl(
    config_module, models_registry, scans
):
    from app.transcriber import model_download_state as dl_state

    scans.result = False
    config_module.get_transcriber_models_status()  # 先填上槽
    dl_state.mark_failed("tiny", "连不上 Hub")
    row = _row(_body(config_module.get_transcriber_models_status()), "tiny")
    assert row["failed"] is True
    assert row["error"] == "连不上 Hub"


# --- 响应契约 ---------------------------------------------------------------


def test_response_shape_is_unchanged(config_module, models_registry, scans):
    scans.result = False
    body = _body(config_module.get_transcriber_models_status())

    assert set(body) == {"whisper", "mlx_whisper", "mlx_available"}
    assert sorted(row["model_size"] for row in body["whisper"]) == ["base", "small", "tiny"]
    for row in body["whisper"]:
        assert set(row) == {"model_size", "downloaded", "downloading", "failed"}
    assert body["mlx_whisper"] == []
    assert body["mlx_available"] == (platform.system() == "Darwin")


def test_downloaded_flag_comes_from_the_scan(config_module, models_registry, scans):
    scans.result = True
    body = _body(config_module.get_transcriber_models_status())
    assert [row["downloaded"] for row in body["whisper"]] == [True, True, True]

    config_module._invalidate_models_status_cache()
    scans.result = False
    body = _body(config_module.get_transcriber_models_status())
    assert [row["downloaded"] for row in body["whisper"]] == [False, False, False]


def test_mlx_rows_are_not_affected_on_non_darwin(config_module, models_registry, scans):
    """mlx 分支只在 Darwin 走；这里钉住「Windows/Linux 上不该出现 mlx 行」。"""
    scans.result = False
    body = _body(config_module.get_transcriber_models_status())
    if platform.system() == "Darwin":
        pytest.skip("本机是 macOS，mlx 分支会真的执行")
    assert body["mlx_whisper"] == []
    assert body["mlx_available"] is False
