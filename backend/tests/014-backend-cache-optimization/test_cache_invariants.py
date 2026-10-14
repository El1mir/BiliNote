"""四条缓存不变量的「合同索引」（spec 014 §测试要点）。

spec 014 引入了一个新的**可变全局状态**：进程内任务状态注册表
（``app/services/task_status_cache.py``）。它只有在下面四条契约同时成立时才是安全的，
而这四条各自依赖一处很容易被后来者改坏的实现细节（删文件时顺手 ``drop``、重试时用
覆盖而不是清空、落盘永远是原子替换……）。所以本文件把它们**各写成一个用例**，
放在一个名字就说明了用途的文件里：任何一条被破坏，失败信息直接指向是哪条契约。

**本文件是「最外层」那一遍**：只走公开入口（HTTP 端点、服务的公开函数），不碰私有
细节，故意写得笨一点。每条不变量在各自 ticket 的测试文件里还有更贴近实现层的用例
（下面每条的 docstring 里点名），**重叠是刻意的** —— 契约文件要能在不读实现的情况下
自证；实现层的用例才会告诉你具体哪一行坏了。

口径：``stat`` 计数可信，``open`` 计数因 ``app/`` 下的 Cython 产物而偏低（见 conftest）。
"""
import json
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.enmus.task_status_enums import TaskStatus
from app.routers import note as note_module
from app.services import task_status_cache
from app.services.note import NoteGenerator


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(note_module.router, prefix="/api")
    return TestClient(app)


def _write_status(results_dir: Path, task_id: str, **fields) -> None:
    payload = {"status": "SUCCESS", "message": "完成", "progress": 100}
    payload.update(fields)
    (results_dir / f"{task_id}.status.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _read(task_id: str) -> dict:
    """走服务的公开读路径（就是 HTTP 端点内部调的那个）。"""
    payload = note_module._read_task_status(task_id, include_result=False, unknown_is_none=True)
    assert payload is not None, f"{task_id} 应当能读到状态，返回了 None"
    return payload


# ---------------------------------------------------------------------------
# ① 删除后不返回旧值
# ---------------------------------------------------------------------------
def test_invariant_1_deleted_task_does_not_come_back(results_dir, monkeypatch):
    """删掉一个任务之后，读者**不能**再看到它删除前的状态。

    机制：删除路径在 ``_delete_artifacts`` 之后调 ``task_status_cache.drop``
    （``app/services/task_cleanup.py`` 的 ``delete_task_completely``）。顺序是刻意的 ——
    先删投影文件、再删内存，否则会开一个「内存已清、磁盘还在」的窗口，期间的轮询会把
    已删除的任务从文件里读回来并重新缓存（症状就是「删了又冒出来」）。

    更深实现层的用例：``test_invalidation_hooks.py`` 的
    ``test_artifacts_are_removed_before_the_registry_is_dropped``、
    ``test_all_delete_paths_share_one_chokepoint``；
    最贴近症状的端到端复现：``test_task_status_memory_authority.py`` 的
    ``test_deleted_task_does_not_reappear_in_batch``。
    """
    from app.services import task_cleanup

    task_id = "inv1-task"
    _write_status(results_dir, task_id)
    monkeypatch.setattr(task_cleanup, "delete_video_task", lambda _tid: 1)

    assert _read(task_id)["status"] == "SUCCESS", "预热失败，注册表里应当是 SUCCESS"
    assert task_status_cache.get(task_id) is not None

    task_cleanup.delete_task_completely(task_id)

    assert task_status_cache.get(task_id) is None, "删除后注册表里还留着旧值"
    assert not (results_dir / f"{task_id}.status.json").exists(), "删除后投影文件还在"
    assert (
        note_module._read_task_status(task_id, include_result=False, unknown_is_none=True) is None
    ), "删除后仍能读到删除前的内容（删了又冒出来）"


# ---------------------------------------------------------------------------
# ② 重试后能看到新状态
# ---------------------------------------------------------------------------
def test_invariant_2_retry_shows_the_new_state(results_dir):
    """重试一个失败的任务后，读者必须立刻看到新状态，而不是注册表里的旧 FAILED。

    机制：重试路径写的是**覆盖**而不是清空 —— ``task_retry.retry_failed_tasks`` 调
    ``NoteGenerator()._update_status(task_id, PENDING, ...)``
    （``backend/app/services/task_retry.py:308``），而 ``_update_status`` 构造的是一份
    **全新完整**的 payload 并 ``put`` 进注册表，旧值被直接盖掉。

    为什么不能改成 ``drop``：清空之后、工作线程第一次写状态之前，磁盘上的旧 FAILED
    文件还在，这期间的任何轮询都会走文件路径把旧值读回来重新缓存 —— 前端表现就是
    「点了重试没反应」。所以重试用的是覆盖，删除用的才是 ``drop``。

    这里直接调 ``_update_status``（重试路径做的就是这一句）；驱动真实入口
    ``retry_failed_tasks()`` 的用例在 ``test_invalidation_hooks.py`` 的
    ``test_retry_overwrites_stale_failure`` 与
    ``test_retry_writes_the_new_state_before_requeueing``。
    """
    task_id = "inv2-task"
    _write_status(results_dir, task_id, status="FAILED", message="下载失败")
    assert _read(task_id)["status"] == "FAILED", "预热失败，注册表里应当是 FAILED"

    NoteGenerator()._update_status(task_id, TaskStatus.PENDING, message="用户手动重试")

    live = _read(task_id)
    assert live["status"] == "PENDING", f"重试后仍读到旧状态：{live['status']}"
    assert live["message"] == "用户手动重试"


# ---------------------------------------------------------------------------
# ③ 重启后能读回
# ---------------------------------------------------------------------------
def test_invariant_3_restart_reads_back_from_the_projection(results_dir):
    """注册表被清空（模拟进程重启）之后，进行中的任务仍必须能从落盘投影读回。

    机制：注册表是**权威**但不是**唯一来源** —— ``_update_status`` 除了 ``put``
    还会原子落盘（``<task_id>.status.json``），``_read_task_status`` 未命中时会回落到
    读文件。少了这条，spec 009 ticket 03 的「重启后恢复任务」就失效了。

    更深实现层的用例：``test_invalidation_hooks.py`` 的
    ``test_registry_restart_reads_back_from_the_projection_file``。
    """
    task_id = "inv3-task"
    _write_status(results_dir, task_id, status="TRANSCRIBING", message="转写中", progress=42)
    assert _read(task_id)["status"] == "TRANSCRIBING", "预热失败"

    task_status_cache.clear()  # 模拟重启

    assert task_status_cache.get(task_id) is None
    assert _read(task_id)["status"] == "TRANSCRIBING", "清空注册表后读不回状态"
    assert task_status_cache.get(task_id) is not None, "回落读文件之后应当把结果填回注册表"


# ---------------------------------------------------------------------------
# ④ 并发不产生半截文件
# ---------------------------------------------------------------------------
def test_invariant_4_concurrent_writers_never_expose_a_partial_file(results_dir):
    """并发写状态时，读者**永远**不会读到半截 JSON 或字段残缺的状态。

    机制有两条，缺一不可：

    * **落盘**：``_update_status`` 写唯一的临时文件 ``<name>.<uuid8>.tmp`` 再
      ``os.replace``（同目录重命名在 Windows 上也是原子的），读者看到的要么是旧的
      完整文件、要么是新的完整文件；
    * **内存**：``_update_status`` 每次从零构造完整 payload，从不读-改-写，所以并发
      写的后果只是「最后写的人赢」，不会有半个状态。GIL 保证 dict 单次 ``__setitem__``
      原子。

    ⚠️ 这两个论证都依赖「每次整份替换」。如果哪天有人把 ``_update_status`` 改成
    读-改-写，本用例仍然会因为字段残缺而失败，但那时正确的修法是**加锁**，而不是
    放宽这个断言。

    **本用例只断言「读到的内容永远是完整的」**，不断言「一定能读到」：Windows 上
    `os.replace` 替换一个正被打开的文件时，读者侧可能瞬时拿到 ``PermissionError``
    （打不开）或 ``FileNotFoundError``（替换窗口内）。那是**能不能读**的问题，
    生产读者（``_read_task_status``）对两者都是容忍的（返回 ``None`` 走占位），
    而且不是写方策略能消除的；写方要负责的是**绝不留下半截内容**。

    上面这条正是本用例抓到过的真问题：``_update_status`` 原来在 ``os.replace``
    失败时会降级成**原地覆盖**，于是并发下读者能读到空文件（``Expecting value:
    line 1 column 1``）—— 实测 121 次。修法见 ``_replace_with_retry`` 与
    ``backend/app/services/note.py`` 里那段「故意不做原地覆盖」的注释。

    更深实现层的用例：``test_task_status_memory_authority.py`` 的
    ``test_concurrent_updates_leave_a_complete_payload`` 与
    ``test_concurrent_readers_never_see_a_partial_payload``。
    """
    generator = NoteGenerator()
    task_id = "inv4-task"
    path = results_dir / f"{task_id}.status.json"
    writers_count, writes_each, readers_count = 6, 20, 3
    torn: list = []
    transient_opens = 0
    stop = threading.Event()

    def writer(index: int) -> None:
        for n in range(writes_each):
            generator._update_status(
                task_id,
                TaskStatus.TRANSCRIBING,
                message=f"writer-{index}-{n}",
                progress=(index * writes_each + n) % 100,
            )

    def reader() -> None:
        nonlocal transient_opens
        while not stop.is_set():
            try:
                raw = path.read_bytes()
            except (FileNotFoundError, PermissionError, OSError):
                transient_opens += 1
                continue
            if not raw:
                # 空文件同样是「半截」——原地覆盖截断后会短暂出现。
                torn.append("投影文件是空的")
                continue
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:  # 半截 JSON 会在这里炸
                torn.append(f"投影文件不是合法 JSON：{exc!r}")
                continue
            if not isinstance(payload, dict) or "status" not in payload:
                torn.append(f"投影文件内容不完整：{payload!r}")
            live = note_module._read_task_status(
                task_id, include_result=False, unknown_is_none=True
            )
            if live is not None and live.get("status") != "TRANSCRIBING":
                torn.append(f"内存读路径给出意外状态：{live!r}")

    readers = [threading.Thread(target=reader, name=f"reader-{i}") for i in range(readers_count)]
    writers = [threading.Thread(target=writer, args=(i,), name=f"writer-{i}") for i in range(writers_count)]
    for thread in readers:
        thread.start()
    for thread in writers:
        thread.start()
    for thread in writers:
        thread.join()
    stop.set()
    for thread in readers:
        thread.join()

    assert not torn, f"{len(torn)} 次读到不完整内容，前几条：{torn[:5]}"
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "TRANSCRIBING"
    assert task_status_cache.get(task_id) is not None
    print(f"（瞬时读失败 {transient_opens} 次，已被生产读者容忍，不计入断言）")
