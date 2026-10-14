"""spec 014 ticket 02：任务状态改「内存权威 + 落盘投影」。

本文件钉死三件事：

1. **快路径真的不碰盘** —— 命中内存时 ``os.path.exists`` 调用数为 0。这是收益的
   全部来源（N=200 同一口径实测：缓存关 p50=162.89ms / 1113 次 stat 每轮；
   缓存开 p50=5.37ms / 12.8 次 stat 每轮。全是同步系统调用，在单进程 uvicorn 里
   每 3 秒阻塞一次事件循环）。
2. **两条读路径的返回体完全一致** —— 无论 payload 来自内存还是 ``.status.json``，
   字段集合必须是同一个契约。否则「命中的和没命中的返回不一样」会成为最难查的
   一类 bug：只在缓存预热后才复现。
3. **内存不被返回体污染** —— 调用方拿到的 dict 若被改动（例如塞入几十 KB 的
   ``result``），注册表里的权威副本必须不受影响。

口径提醒（见 conftest.py 的说明）：``app/`` 下有 Cython 编译产物，C 实现绕过
``builtins.open``，所以 **``open`` 计数偏低，``stat`` 计数才可信**。本文件的
「是否碰盘」断言一律数 ``os.path.exists``。
"""

import json
import threading

import pytest

from app.routers import note as note_module
from app.services import note as note_service
from app.services import task_cleanup, task_status_cache

#: 一条成功任务在 ``.status.json`` 里的典型内容（216 字节量级，见 spec §12.1）。
_SUCCESS_ON_DISK = {
    "status": "SUCCESS",
    "stage": "success",
    "stage_label": "已完成",
    "progress": 100,
    "stage_progress": 100,
    "message": "",
    "detail": {},
    "updated_at": "2026-10-14T12:00:00+00:00",
}


@pytest.fixture
def stat_counter(monkeypatch):
    """数 ``os.path.exists`` 的调用次数。

    只包 ``note_module`` 用的那个 ``os.path`` 就是全局的 ``os.path``（Python 里
    ``os.path`` 是单例模块），所以这里用「先归零再调用」的方式把观测窗口收窄到
    被测函数那一段，避免把 pytest 自己的 stat 算进来。
    """

    class Counter:
        def __init__(self):
            self.calls = 0

        def reset(self):
            self.calls = 0

    counter = Counter()
    real_exists = note_module.os.path.exists

    def counting_exists(path):
        counter.calls += 1
        return real_exists(path)

    monkeypatch.setattr(note_module.os.path, "exists", counting_exists)
    return counter


def _write_status(results_dir, task_id, payload=None):
    body = dict(_SUCCESS_ON_DISK) if payload is None else payload
    (results_dir / f"{task_id}.status.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8"
    )
    return body


def _write_result(results_dir, task_id, markdown="# 笔记"):
    body = {"markdown": markdown, "transcript": [], "title": "标题"}
    (results_dir / f"{task_id}.json").write_text(
        json.dumps(body, ensure_ascii=False), encoding="utf-8"
    )
    return body


def _read(task_id: str, **kwargs) -> dict:
    """``_read_task_status`` 的测试用包装：断言拿得到状态后再返回。

    只为让类型检查器把返回类型从 ``dict | None`` 收窄 —— 语义与直接调用完全一致。
    """
    payload = note_module._read_task_status(task_id, **kwargs)
    assert payload is not None, f"{task_id} 应当有状态"
    return payload


def _cached(task_id: str) -> dict:
    """取注册表里的权威副本（取不到直接失败）。"""
    payload = task_status_cache.get(task_id)
    assert payload is not None, f"注册表里没有 {task_id}"
    return payload


# ------------------------------------------------------------------ 快路径


def test_memory_hit_does_not_touch_disk(results_dir, stat_counter):
    """命中内存时零 stat —— 这是整个 ticket 的验收核心。"""
    task_id = "t-hit"
    _write_status(results_dir, task_id)
    # 先预热一次（走文件路径），随后删掉文件：如果还去查盘，这里会退化成
    # unknown / pending，测试就会失败，而不会静默通过。
    first = _read(task_id, include_result=False)
    assert first["status"] == "SUCCESS"
    (results_dir / f"{task_id}.status.json").unlink()

    stat_counter.reset()
    second = _read(task_id, include_result=False)

    assert stat_counter.calls == 0, f"命中内存却查了 {stat_counter.calls} 次盘"
    assert second["status"] == "SUCCESS"


def test_file_read_populates_memory(results_dir):
    """未命中时必须回落文件，并把结果放进注册表供下一次轮询命中。"""
    task_id = "t-fill"
    _write_status(results_dir, task_id)
    assert task_status_cache.get(task_id) is None

    note_module._read_task_status(task_id, include_result=False)

    cached = task_status_cache.get(task_id)
    assert cached is not None
    assert cached["status"] == "SUCCESS"


def test_cache_off_falls_back_to_disk_every_time(results_dir, stat_counter, cache_off):
    """``BILINOTE_CACHE=off`` 时每一次都要真的读盘（对比测量的前提）。"""
    task_id = "t-off"
    _write_status(results_dir, task_id)

    note_module._read_task_status(task_id, include_result=False)
    stat_counter.reset()
    note_module._read_task_status(task_id, include_result=False)

    assert stat_counter.calls > 0, "关掉开关后仍然命中内存，开关没有生效"
    assert task_status_cache.get(task_id) is None


def test_unknown_task_is_not_cached(results_dir):
    """未知 id 返回 None，且**不**在注册表里留下痕迹。

    否则一个被删掉的 id 会永远返回「什么都不是」，而它后面可能被重新创建。
    """
    assert note_module._read_task_status("t-nope", unknown_is_none=True) is None
    assert task_status_cache.get("t-nope") is None


def test_pending_placeholder_is_not_cached(results_dir):
    """「排队中」占位表达的只是「没有任何落盘痕迹」，不是权威状态。"""
    state = _read("t-queued", unknown_is_none=False)
    assert state["status"] == "PENDING"
    assert task_status_cache.get("t-queued") is None


# ------------------------------------------------------- 两条路径的契约一致


def test_both_read_paths_expose_the_same_field_set(results_dir):
    """内存路径与文件路径返回的键集合必须完全相同。"""
    task_id = "t-parity"
    _write_status(results_dir, task_id)

    from_file = _read(task_id, include_result=False)
    task_status_cache.clear()
    _write_status(results_dir, task_id)
    from_memory_seed = _read(task_id, include_result=False)
    from_memory = _read(task_id, include_result=False)

    assert set(from_file) == set(from_memory) == set(from_memory_seed)


def test_synthesized_success_when_only_result_file_exists(results_dir):
    """状态文件缺失、结果文件在（历史遗留）时合成 SUCCESS，并进注册表。"""
    task_id = "t-legacy"
    _write_result(results_dir, task_id)

    payload = _read(task_id, include_result=False)

    assert payload["status"] == "SUCCESS"
    assert payload["progress"] == 100
    assert _cached(task_id)["status"] == "SUCCESS"


def test_missing_message_falls_back_to_empty_string(results_dir):
    """磁盘上缺 ``message`` 时补空串——两条路径都要补。"""
    task_id = "t-nomsg"
    body = {k: v for k, v in _SUCCESS_ON_DISK.items() if k != "message"}
    _write_status(results_dir, task_id, body)

    from_file = _read(task_id, include_result=False)
    from_memory = _read(task_id, include_result=False)

    assert from_file["message"] == ""
    assert from_memory["message"] == ""


# ------------------------------------------------------------ 内存不被污染


def test_result_payload_never_enters_registry(results_dir):
    """``include_result=True`` 拉详情时，几十 KB 的 result 不能进注册表。

    注册表存的是 216 字节量级的状态；一旦被 result 撑大，常驻内存就没有上限了。
    """
    task_id = "t-result"
    _write_status(results_dir, task_id)
    _write_result(results_dir, task_id, markdown="# 很大的笔记" * 100)

    payload = _read(task_id, include_result=True)

    assert payload["result"]["markdown"].startswith("# 很大的笔记")
    assert "result" not in _cached(task_id)


def test_mutating_returned_payload_does_not_pollute_registry(results_dir):
    """调用方改自己拿到的那份 dict，不能影响注册表里的权威副本。"""
    task_id = "t-mutate"
    _write_status(results_dir, task_id)
    _write_result(results_dir, task_id)

    first = _read(task_id, include_result=True)
    first["status"] = "FAILED"
    first["result"]["markdown"] = "被调用方改掉了"

    second = _read(task_id, include_result=False)

    assert second["status"] == "SUCCESS"
    assert "result" not in _cached(task_id)


# ------------------------------------------------------------ 写路径与失效


def test_update_status_writes_memory(results_dir):
    """``_update_status`` 必须让注册表立刻拿到新状态（内存是权威副本）。"""
    note_service.NoteGenerator()._update_status("t-write", "TRANSCRIBING")

    cached = task_status_cache.get("t-write")
    assert cached is not None
    assert cached["status"] == "TRANSCRIBING"
    assert cached["task_id"] == "t-write"


def test_update_status_puts_before_writing_disk(results_dir, monkeypatch):
    """落盘失败也不能丢掉内存更新 —— 证明 put 发生在写盘之前。

    用「让 ``json.dump`` 抛异常」来模拟磁盘故障。落盘是**投影**，它失败只该影响
    「重启后能否读回」，不该影响本次运行的正确性。
    """

    def boom(*args, **kwargs):
        raise OSError("磁盘满了")

    monkeypatch.setattr(note_service.json, "dump", boom)

    note_service.NoteGenerator()._update_status("t-order", "SUMMARIZING")

    assert _cached("t-order")["status"] == "SUMMARIZING"


def test_update_status_overwrites_stale_memory(results_dir):
    """整份替换语义：新状态必须完整覆盖旧的，不留上一个状态的字段。"""
    generator = note_service.NoteGenerator()
    generator._update_status("t-over", "TRANSCRIBING", detail={"current": 1, "total": 9})
    generator._update_status("t-over", "SUCCESS")

    cached = _cached("t-over")
    assert cached["status"] == "SUCCESS"
    # detail 是整份重建的：第二次没传就应该是空 dict，不该残留上一次的计数。
    assert cached["detail"] == {}


def test_delete_task_completely_drops_memory(results_dir, monkeypatch):
    """删除必须同步清内存（否则症状是「删了又冒出来」）。"""
    task_id = "t-del"
    _write_status(results_dir, task_id)
    note_module._read_task_status(task_id, include_result=False)
    assert task_status_cache.get(task_id) is not None

    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    task_cleanup.delete_task_completely(task_id)

    assert task_status_cache.get(task_id) is None
    assert note_module._read_task_status(task_id, unknown_is_none=True) is None


def test_deleted_task_does_not_reappear_in_batch(results_dir, monkeypatch):
    """端到端复现「删了又冒出来」：删除后批量端点必须返回 null。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    task_id = "t-ghost"
    _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)
    monkeypatch.setattr(note_module, "_task_row_exists", lambda _tid: False)

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    client = TestClient(app)

    # 先预热注册表（模拟删除前前端已经轮询过）。
    note_module._read_task_status(task_id, include_result=False)
    task_cleanup.delete_task_completely(task_id)

    body = client.post("/api/task_status/batch", json={"task_ids": [task_id]}).json()
    assert body["code"] == 0, body
    assert body["data"]["states"][task_id] is None


def test_batch_endpoint_touches_no_disk_when_warm(results_dir, stat_counter):
    """ticket 02 的验收核心在 HTTP 层的复现 —— 预热后的批量轮询一次盘都不查。

    上面那条 ``test_memory_hit_does_not_touch_disk`` 只证明了单个函数；真正决定
    前端体验的是 ``POST /api/task_status/batch`` 这条路径（200 条时缓存关
    p50=162.89ms / 1113 次 stat 每轮，缓存开 p50=5.37ms / 12.8 次）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    task_ids = [f"t-poll-{i:03d}" for i in range(50)]
    for task_id in task_ids:
        _write_status(results_dir, task_id)

    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    client = TestClient(app)

    warm = client.post("/api/task_status/batch", json={"task_ids": task_ids})
    assert warm.status_code == 200
    assert all(task_status_cache.get(tid) is not None for tid in task_ids)

    stat_counter.reset()
    resp = client.post("/api/task_status/batch", json={"task_ids": task_ids})
    assert resp.status_code == 200
    states = resp.json()["data"]["states"]
    assert all(states[tid]["status"] == "SUCCESS" for tid in task_ids), states
    assert stat_counter.calls == 0, f"命中内存却查了 {stat_counter.calls} 次盘"


# ---------------------------------------------------------------- 并发写入

def test_concurrent_updates_leave_a_complete_payload(results_dir):
    """8 个截图线程并发写：最终值必须是**某一次完整写入**，不能是拼接体。

    这是「不加锁」论证的回归保护。它不能证明没有竞态，但能钉住「整份替换」这个
    前提本身——一旦有人把 ``_update_status`` 改成读-改-写，这个用例通常就会开始
    出现缺字段的失败。
    """
    generator = note_service.NoteGenerator()
    task_id = "t-race"
    light_keys = set(note_module._STATUS_LIGHT_KEYS) | {"task_id"}

    def worker(index):
        generator._update_status(
            task_id,
            "TRANSCRIBING",
            message=f"worker-{index}",
            stage_progress=index,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    cached = task_status_cache.get(task_id)
    assert cached is not None
    assert light_keys <= set(cached), f"并发写入丢了字段：{set(cached)}"
    assert cached["message"] in {f"worker-{i}" for i in range(8)}
    assert cached["status"] == "TRANSCRIBING"


def test_concurrent_readers_never_see_a_partial_payload(results_dir):
    """并发读的同时持续写，读者拿到的永远是一个完整 payload。"""
    generator = note_service.NoteGenerator()
    task_id = "t-race-read"
    light_keys = set(note_module._STATUS_LIGHT_KEYS) | {"task_id"}
    stop = threading.Event()
    problems = []

    def writer():
        index = 0
        while not stop.is_set():
            generator._update_status(task_id, "TRANSCRIBING", message=f"m{index}")
            index += 1

    def reader():
        while not stop.is_set():
            payload = task_status_cache.get(task_id)
            if payload is None:
                continue
            missing = light_keys - set(payload)
            if missing:
                problems.append(missing)
                return

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    stop.wait(0.4)
    stop.set()
    for thread in threads:
        thread.join()

    assert not problems, f"读者看到了不完整的 payload：{problems[:3]}"


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "Off", "no", " off "])
def test_falsy_switch_values_disable_memory_path(value, results_dir, monkeypatch):
    """开关的取值表（大小写与空白不敏感）——写死以免日后被「优化」掉。"""
    monkeypatch.setenv("BILINOTE_CACHE", value)
    _write_status(results_dir, "t-flag")

    note_module._read_task_status("t-flag", include_result=False)

    assert task_status_cache.get("t-flag") is None
