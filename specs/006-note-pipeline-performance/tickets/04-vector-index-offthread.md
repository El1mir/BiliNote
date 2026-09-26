# 04 · 向量索引移出任务关键路径

- **依赖**：—
- **关联**：spec §4 决策 9
- **状态**：已完成

## 目标

`routers/note.py::run_note_task()` 在写 `SUCCESS` 之后**同步**执行
`VectorStoreManager().index_task(task_id)`（含 chromadb 建 collection + 嵌入，实机 2s+）。
它不改变任务结果，却占着任务工作线程（`TASK_MAX_WORKERS=5`），排队的任务因此被拖慢。

## 改动点

1. `vector_store.py` 暴露模块级后台执行器（`ThreadPoolExecutor(max_workers=2, thread_name_prefix="vector-index")`）
   与 `index_task_in_background(task_id)`：提交任务并在异常时 `logger.warning` 记录，绝不抛出。
2. `routers/note.py::run_note_task()` 改为调用后台版本，删除同步 `try/except + warning` 块。
3. 保持顺序约束：必须仍在 `save_note_to_file()` **之后**提交（索引读取 `<task_id>.json`）。
4. 进程退出时不阻塞等待索引完成（`daemon` 语义由 ThreadPoolExecutor + 主进程退出保证）。

## 验收

- 任务 `SUCCESS` 的时刻不再包含索引耗时（日志时间差可验证）。
- 索引失败只出现 warning，任务仍为 `SUCCESS`。
- 索引完成后 `/api/chat` 的检索行为不变。
