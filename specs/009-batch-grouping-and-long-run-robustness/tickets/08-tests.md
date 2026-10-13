# 08 · 测试与回归网

- **依赖**：01–07
- **关联**：spec §6
- **状态**：已完成

## 目标

为本 spec 的每条验收标准建立可执行的回归网，并补齐既有空白（`backend/tests/001-bilibili-batch-import/test_batch_generate_api.py` 完全不覆盖 `group_name` 建组路径；**全仓无任何 `test_general*.py`**；无任何负载/压力测试）。

## 改动点

1. 新建目录 `backend/tests/009-batch-grouping-and-long-run-robustness/`，用例文件：
   - `test_batch_grouping.py`（ticket 01）
   - `test_parallel_scheduler.py`（ticket 02：批内并发 >1 且 ≤ `max_parallel_notes`；闸门 reconfigure 扩容唤醒阻塞线程、缩容归还名额）
   - `test_startup_requeue.py` + 迁移用例（ticket 03）
   - `test_disk_gate.py`、`test_circuit_breaker.py`（ticket 04）
   - `test_sqlite_pragma.py`、`test_video_task_index.py`、`test_cookie_temp_cleanup.py`（ticket 05）
   - `test_task_status_batch.py`（ticket 06）
   - `test_cache_limit_cleanup.py`、`test_general_settings_cache_fields.py`（ticket 07）
2. 补一条 `group_name` 建组回归用例到 `backend/tests/001-bilibili-batch-import/test_batch_generate_api.py`（或并入 `test_batch_grouping.py` 并在其中注明）。
3. 测试约定（沿用仓库现状）：
   - **无 conftest.py / pytest.ini**，各用例自带 fixture；
   - `ResponseWrapper.error` 的 HTTP 层是 200，错误码在 body 的 `code` 字段 —— 断言一律看 `code`（见 `backend/tests/007-note-archive-and-media-cache/test_note_group_api.py:15-17`）；
   - 临时 SQLite + `monkeypatch.setattr(engine_module, "SessionLocal", factory)` 的写法见 `test_note_group_api.py:41-60` 与 `test_media_resources.py` 的 `media_env` fixture；
   - `monkeypatch.setattr(note_module, "task_serial_executor", ...)` 的写法见 `backend/tests/001-bilibili-batch-import/test_task_retry.py`。
4. 不得破坏的既有断言：
   - `test_note_group_api.py:277`「删组不删任务」（`all(row["group_id"] is None ...)`）；
   - `test_note_group_api.py:338-360` `""` / `'__unattached__'`→ 三值都落 `group_id IS NULL`；
   - `test_media_resources.py` 的路径穿越防护；
   - `test_in_flight_dedup.py` 的状态集合。
5. 长批量冒烟（不引入新依赖）：用假 generator（不真的下载/转写）提交 200 条，断言并发受控、进程内存与线程数不爆、轮询只发一次请求。

## 验收

- 新增用例全部通过；既有后端测试无回归。
- 前端 `pnpm test` / `pnpm build` 通过。
- 每条 spec §6 验收标准都能对应到至少一条用例或一个人工验证步骤（在实现说明里列出对应关系）。
