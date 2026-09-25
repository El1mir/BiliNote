# 09 · 并发隔离：去重纳入「进行中」状态

- **依赖**：03
- **关联**：spec §6（修订）/ §12
- **状态**：✅ 已完成

## 目标

同一视频在任务进行中时不再重复起任务，避免并发互踩临时文件。

## 改动点

1. `backend/app/routers/note.py`
   - 抽出 `_get_task_record(video_id, platform) -> (task_id, status)`；
   - `_is_generated_task` = status 为 `SUCCESS`；
   - 新增 `_is_task_in_flight` = status 属于 `_IN_FLIGHT_STATUSES`
     （PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/FORMATTING/SAVING）；
2. `POST /api/generate_notes`：命中进行中 → `skipped (reason=in_progress)`；
3. `POST /api/generate_note`：非重试模式命中进行中 → 返回 300103「该视频正在生成中，请稍候」。

## 验收

- 进行中状态被识别为 in-flight，`SUCCESS` / `FAILED` 不是；
- 批量提交进行中的视频不产生新任务；
- 单条提交进行中的视频返回明确错误而不是再起一个任务。

## 测试

`backend/tests/001-bilibili-batch-import/test_in_flight_dedup.py`
`backend/tests/001-bilibili-batch-import/test_batch_skips_in_progress.py`
