"""``BILINOTE_CACHE`` 开关的语义。

为什么值得单独一个文件：spec 014 的所有前后对比数字都建立在
``baseline_measure.py --cache both`` 的两个腿上 —— 「关」那一腿被当作**改动前的对照
组**。这个等式只有在开关真的绕过内存快路径时才成立；如果 ``off`` 没生效，对照组就是
假的，收益数字会失真。所以开关的语义本身需要有独立证据。

三条语义（``app/services/task_status_cache.py``）：

1. ``off`` 时 ``get()`` 恒返回 ``None`` —— 每次读都回落到文件路径；
2. ``on`` 时命中就不碰盘；
3. 开关是**每次调用读环境变量**的，不是导入时固化 —— 所以同一次运行内能做到
   「先关后开」，这也是测量脚本能在一次进程里跑出两条腿的原因。

另有一条反直觉但刻意的语义，也在下面钉住：``off`` **只影响 ``get``，不影响 ``put``**
（``_update_status`` 照旧写注册表）。这样「关着跑一轮、再打开」不会有一段全冷的窗口。
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import note as note_module
from app.services import task_status_cache

ROWS = 30


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app)


def _seed(results_dir: Path, count: int) -> list:
    task_ids = []
    for index in range(count):
        task_id = f"sw-{index:03d}"
        (results_dir / f"{task_id}.status.json").write_text(
            json.dumps({"status": "SUCCESS", "message": "完成"}, ensure_ascii=False),
            encoding="utf-8",
        )
        task_ids.append(task_id)
    return task_ids


def _poll(client: TestClient, task_ids: list) -> None:
    resp = client.post("/api/task_status/batch", json={"task_ids": task_ids})
    assert resp.status_code == 200, resp.text


def test_off_makes_every_poll_touch_the_disk(results_dir, counter, monkeypatch):
    """``off`` 时一轮批量轮询的 ``stat`` 必须在「每任务至少一次」的量级。

    这就是测量脚本里那根对照组的依据。
    """
    import os

    monkeypatch.setenv("BILINOTE_CACHE", "off")
    task_ids = _seed(results_dir, ROWS)
    client = _client()
    _poll(client, task_ids)  # 预热（off 下预热也填注册表，但读照样走盘）

    monkeypatch.setattr(os, "stat", counter.of(os.stat))
    _poll(client, task_ids)

    assert counter.calls >= ROWS, (
        f"off 下这一轮只 stat 了 {counter.calls} 次，少于 {ROWS} 个任务 —— 开关没有真的绕过快路径"
    )


def test_on_makes_a_warm_poll_touch_nothing(results_dir, counter, monkeypatch):
    """默认（``on``）时，预热过后一轮批量轮询的 ``stat`` 必须是 0。"""
    import os

    task_ids = _seed(results_dir, ROWS)
    client = _client()
    _poll(client, task_ids)

    monkeypatch.setattr(os, "stat", counter.of(os.stat))
    _poll(client, task_ids)

    assert counter.calls == 0, f"命中缓存后仍 stat 了 {counter.calls} 次"


def test_switch_is_read_on_every_call(results_dir, counter, monkeypatch):
    """开关不是导入时固化的：同一个进程里「先关后开」必须立刻生效。

    这也是测量脚本能在一次运行里跑出两条腿的原因；若开关被缓存到模块级，两条腿会
    互相污染，整个前后对比都不可信。
    """
    import os

    monkeypatch.setenv("BILINOTE_CACHE", "off")
    task_ids = _seed(results_dir, ROWS)
    client = _client()
    _poll(client, task_ids)

    monkeypatch.setattr(os, "stat", counter.of(os.stat))
    _poll(client, task_ids)
    assert counter.calls > 0, "off 下这一轮竟然没读盘"

    monkeypatch.delenv("BILINOTE_CACHE")
    counter.reset()
    _poll(client, task_ids)

    assert counter.calls == 0, (
        f"删掉环境变量后这一轮仍 stat 了 {counter.calls} 次 —— 开关被固化在了导入期"
    )


def test_off_only_gates_reads_not_writes(results_dir, cache_off):
    """``off`` 只挡 ``get``，不挡 ``put``。

    刻意如此：这样「关着跑一轮再打开」不会出现一段全冷的窗口。副作用是注册表会在
    ``off`` 期间照样被填满 —— 也是 ``test_switch_is_read_on_every_call`` 里
    「删掉环境变量后立刻零 stat」能成立的另一半原因。
    """
    from app.enmus.task_status_enums import TaskStatus
    from app.services.note import NoteGenerator

    task_id = "sw-write"
    NoteGenerator()._update_status(task_id, TaskStatus.TRANSCRIBING, message="转写中")

    assert task_status_cache.disabled() is True
    assert task_status_cache.get(task_id) is None, "off 时 get 不该返回内容"
    assert task_id in task_status_cache._store, "off 时 put 仍应写入注册表"
