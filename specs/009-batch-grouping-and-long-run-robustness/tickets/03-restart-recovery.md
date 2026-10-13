# 03 · 重启恢复：`payload_json` 列、迁移与启动重入队

- **依赖**：02
- **关联**：spec §4 决策 8–10、§6
- **状态**：已完成

## 目标

进程重启后，被中断的在途任务自动重新开始执行，且使用当初提交的生成参数。

## 背景

`<task_id>.status.json`（`backend/app/services/note.py:1439-1448`）只存 `status/stage/stage_label/progress/stage_progress/message/detail/updated_at`，**不含任何生成参数**；`video_tasks` 也只有 `video_id/platform/task_id/group_id/created_at`。因此重启恢复无法还原 quality / model / provider / screenshot 等参数。同时全仓 `resume|requeue|recover` 零命中，重启后 PENDING/TRANSCRIBING 任务永久僵死，且因 `_IN_FLIGHT_STATUSES` 含 PENDING（`note.py:234-242`），这些视频连重新提交都被拒。

## 改动点

1. `backend/app/db/models/video_tasks.py`：新增 `payload_json` 列（`Text`，nullable），存放提交时的完整生成参数 JSON。
2. `backend/app/db/init_db.py`：在既有幂等增量迁移块内补 `ALTER TABLE video_tasks ADD COLUMN payload_json TEXT`（`create_all` 不给已有表加列，参照 `init_db.py:52-56` 的 group_id 写法）。
3. `backend/app/db/video_task_dao.py`：
   - `insert_video_task` 增加 `payload_json` 可选参数并写入；
   - `list_video_tasks` 返回该字段（或新增查询函数），供启动恢复读取。
4. `backend/app/routers/note.py` `_enqueue_task`（`:490-515`）：提交时把完整参数序列化写入 `payload_json`。批量与单条共用。
5. 新增启动恢复逻辑（`backend/main.py` 的 lifespan 内，或独立 service）：
   - 扫描 `video_tasks` 中**在途状态**（PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/FORMATTING/SAVING）的任务；
   - 用 `payload_json` 还原参数并重新入队，走**同一个闸门调度**（不另做启动专用节流）；
   - **FAILED 不动**；
   - 必须在 `init_db()` 之后、且不阻塞启动：沿用 `main.py:77-85` 已有的 `asyncio.create_task` 模式，并与 `media_cleanup_loop` 一样在 lifespan 的 finally 里 `stop`。
   - 幂等保护：避免同一 task_id 被恢复两次（例如重启瞬间正在恢复时又被恢复）。
6. 恢复后的任务状态应回到 PENDING 并写入一条可辨识的 message（例如「重启后自动恢复」）。

## 验收

- 造一个在途状态的任务 → 重启后端 → 该任务自动重新开始执行，且参数与当初一致。
- FAILED 的任务不被自动重跑。
- 恢复不阻塞启动日志（启动 5 步日志仍按顺序输出）。
- 重复启动不会重复入队同一任务。

## 测试

- 新增 `test_startup_requeue.py`：伪造 `video_tasks` 行 + 状态文件，断言只恢复在途状态、参数从 `payload_json` 还原、FAILED 被跳过。
- 新增迁移用例：老库（无 `payload_json`）经 `init_db()` 后该列存在。
