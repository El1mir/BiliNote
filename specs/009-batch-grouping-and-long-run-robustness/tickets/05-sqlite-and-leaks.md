# 05 · SQLite WAL/busy_timeout、`video_tasks` 索引、cookie 文件泄漏

- **依赖**：无
- **关联**：spec §1 其余已确认缺陷、§6
- **状态**：已完成

## 目标

消除长批量下的写锁冲突与去重全表扫；不再泄漏含凭据的临时文件。

## 改动点

1. **SQLite PRAGMA**（全仓目前零命中，见 `backend/app/db/engine.py` 全文）：
   - 在 `engine.py` 为 sqlite 连接注册 `PRAGMA journal_mode=WAL` 与 `PRAGMA busy_timeout=<ms>`（建议 5000–10000）；
   - `backend/app/db/sqlite_client.py:1-4` 的裸 `sqlite3.connect("bili_note.db")` 同样补 `busy_timeout`；
   - 只对 `engine.dialect.name == "sqlite"` 生效，不改变非 sqlite 的池参数（`engine.py:16-22`）。
   - 注意：WAL 会产生 `-wal` / `-shm` 伴生文件，`scripts/reset_local_state.py` 与 `.gitignore` 需确认不受影响。
2. **`video_tasks` 索引**：为 `(video_id, platform)` 建索引（去重探测 `get_task_by_video`（`video_task_dao.py:49-72`）目前全表扫）。通过 `backend/app/db/models/video_tasks.py` 的 `__table_args__` 声明，并在 `init_db.py` 补 `CREATE INDEX IF NOT EXISTS` 幂等迁移。
3. **cookie 文件泄漏**：`backend/app/downloaders/bilibili_downloader.py:37-51` 的 `_write_netscape_cookie_file` 用 `tempfile.NamedTemporaryFile(..., delete=False)`（`:47`），**全仓无删除点**。改为在下载器实例销毁/下载结束（成功或失败）后删除该文件；同时确认 `delete_video`（`:272-280`）这类既有清理路径是否也需要接上。
   - 临时文件含 live SESSDATA，删除必须走 `finally`，避免异常路径泄漏。

## 验收

- 并发写库不再出现 `sqlite3.OperationalError: database is locked`（或显著降低）。
- 去重查询走索引（可用 `EXPLAIN QUERY PLAN` 断言）。
- 一次生成任务结束后，`%TEMP%` 不残留新增的 `*.txt` cookie 文件；异常路径同样不残留。

## 测试

- `test_sqlite_pragma.py`：断言连接上 `journal_mode` 为 `wal`、`busy_timeout` 生效。
- `test_video_task_index.py`：断言索引存在。
- `test_cookie_temp_cleanup.py`：调用下载器后断言临时 cookie 文件被删除（含抛异常路径）。
