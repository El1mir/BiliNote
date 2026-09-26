"""spec 006 ticket 04：向量索引移出任务关键路径。

建立索引（chromadb + embedding，2s 级）不属于任务结果的一部分：
  * 提交后立即返回，不占用任务工作线程（TASK_MAX_WORKERS 有限）；
  * 真正执行发生在独立线程池（thread_name_prefix="vector-index"）；
  * 失败只告警，绝不影响任务终态；
  * run_note_task() 调用的是后台提交函数，而不是同步 VectorStoreManager().index_task()。
"""
import ast
import pathlib
import threading
import time

from app.services import vector_store

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_index_task_in_background_does_not_block(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    seen = {}

    class FakeVectorStoreManager:
        def index_task(self, task_id):
            seen["task_id"] = task_id
            seen["thread"] = threading.current_thread().name
            started.set()
            release.wait(5)

    monkeypatch.setattr(vector_store, "VectorStoreManager", FakeVectorStoreManager)

    began = time.perf_counter()
    vector_store.index_task_in_background("task-1")
    elapsed = time.perf_counter() - began

    try:
        assert elapsed < 0.5, "提交索引不能阻塞任务线程"
        assert started.wait(5), "索引应在后台线程里执行"
        assert seen["task_id"] == "task-1"
        assert seen["thread"].startswith("vector-index")
    finally:
        release.set()


def test_index_failure_is_only_a_warning(monkeypatch):
    warnings = []

    class BoomVectorStoreManager:
        def index_task(self, task_id):
            raise RuntimeError("chroma 挂了")

    monkeypatch.setattr(vector_store, "VectorStoreManager", BoomVectorStoreManager)
    monkeypatch.setattr(
        vector_store.logger, "warning", lambda message, *args, **kwargs: warnings.append(message)
    )

    vector_store.index_task_in_background("task-2")

    deadline = time.time() + 5
    while not warnings and time.time() < deadline:
        time.sleep(0.02)

    assert warnings, "后台索引失败必须记录告警"
    assert "task-2" in warnings[0]


def test_executor_is_a_dedicated_small_pool():
    executor = vector_store._vector_index_executor
    assert executor._max_workers == 2
    assert executor._thread_name_prefix == "vector-index"


def test_run_note_task_schedules_indexing_in_background():
    source = (ROOT / "app" / "routers" / "note.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_note_task":
            calls = [ast.unparse(call.func) for call in ast.walk(node) if isinstance(call, ast.Call)]
            assert "index_task_in_background" in calls, "run_note_task 应该后台提交索引"
            assert not any(name.endswith(".index_task") for name in calls), "索引不能再同步执行"
            break
    else:
        raise AssertionError("找不到 run_note_task")
