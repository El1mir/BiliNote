# 02 · 真并发调度器与闸门修复、默认并发 3

- **依赖**：无
- **关联**：spec §4 决策 6–7、§6
- **状态**：已完成

## 目标

单次批量内的任务真正并发执行，并发度受 `max_parallel_notes` 约束；运行期调整并发数不会遗弃阻塞线程或永久吞掉名额。

## 背景（关键机制）

`backend/app/routers/note.py:831-853` 逐条 `background_tasks.add_task(run_note_task, ...)`，而 Starlette `BackgroundTasks.__call__` 是 `for task in self.tasks: await task()` —— **严格串行**。所以单次批量内 `_ParallelGate` 与 `task_serial_executor` 根本不被争用，200 个任务实际并发度 = 1。

## 改动点

1. 批量入口（`POST /api/generate_notes`）不再逐条挂后台任务；改为把每条交给一个**受闸门约束的调度**：先在**池外** `gate.acquire()`（沿用 `note.py:323-337` 既有注释约束「闸门必须在池外面，否则任务占着 worker 空转等门闩」），拿到名额后再提交线程池，任务结束时归还名额。
2. 保持 `_run_with_parallel_gate` 的语义（gate → pool → release），确保单条入口（`POST /api/generate_note`）与批量入口共用同一套闸门与池。
3. 修复 `_ParallelGate`（`note.py:148-200`）：
   - 扩容路径**不得**替换 `BoundedSemaphore` 对象（`note.py:169-172` 会遗弃已阻塞线程）——改为在同一个信号量上补放额外名额；
   - 缩容路径（`note.py:174-183`）占掉的名额必须在真正释放时归还，`release_excess()`（`note.py:185-192`）当前**零调用点**，需接上或重写该逻辑。
4. `backend/app/db/models/general_settings.py:12`：`DEFAULT_MAX_PARALLEL_NOTES` 1 → **3**；`MAX_PARALLEL_NOTES_LIMIT` 保持 8。
5. 若需要新的调度辅助类，放在 `backend/app/services/` 下（不要塞进 `routers/note.py`），并保留 `task_serial_executor` 单例以兼容现有测试（`backend/tests/test_task_serial_executor.py`、`backend/tests/001-bilibili-batch-import/test_task_retry.py` 会 `monkeypatch` 它）。

## 验收

- 单次批量 200 条时，同时执行的任务数受 `max_parallel_notes` 约束（默认 3），不是串行 1 个。
- 运行期调大并发 → 新任务立刻按新并发执行；调小 → 不会永久吞掉名额。
- 单条入口行为不变。

## 测试

- 新增用例：提交 N 条批量后断言同时处于执行态的任务数 ≤ `max_parallel_notes`，且 > 1。
- 新增用例：`_ParallelGate.reconfigure` 扩容后，先前阻塞的线程能被唤醒；缩容后归还名额可再次获取。
- 现有 `backend/tests/001-bilibili-batch-import/test_in_flight_dedup.py`、`test_batch_skips_in_progress.py` 必须继续通过。
