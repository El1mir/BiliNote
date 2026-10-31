# 03 合并任务执行与恢复

- 依赖：02
- 关联 spec：§4 决策 3/6/9、§5.2
- 目标：一条任务内跑完 N 个视频并合并；重启后能按原参数重跑。

## 改动点

- `run_note_task` 新增 `merge_items` / `merge_title` / `merge_polish` 参数，命中时转
  `_run_merged_note_task(...)`：
  - 每条用内部 task_id `<task_id>-s{i}` 跑 `NoteGenerator.generate(persist_metadata=False)`；
  - 每条前写状态 `message="合并生成 i/N：标题"`、`progress` 按条推进；
  - 收集 markdown/转写/时长，调用 `note_merge` 合并，`save_note_to_file(task_id, merged)`；
  - 失败清单进笔记末尾 + 状态消息；全失败判 FAILED；
  - 收尾删除 `-s{i}` 状态文件。
- `NoteGenerator.generate` 增加 `persist_metadata: bool = True`，合并子任务不写任务行。
- `backend/app/services/task_recovery.py` 的 `_PAYLOAD_KEYS` 增加三个 merge 字段；
  `_fallback_payload` 不处理合并（缺 payload 的合并行跳过并记日志）。

## 验收

- 8 条里 1 条失败：任务 SUCCESS，笔记末尾出现「未生成成功的视频」。
- 8 条全失败：任务 FAILED。
- 重启后 `payload_json` 含 `merge_items` 的行被重新派发。
