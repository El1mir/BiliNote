# 14 · 任务 ID 贯穿全流程（修复幻影状态文件与 90% 冻结）

- **依赖**：—
- **关联**：spec §5
- **状态**：已完成
- **日期**：2026-09-26（实机排查 BV1E7wtzaEdq 任务时发现）

## 背景

`NoteGenerator.generate()` 只在入口拿到真实 `task_id`，进入内层方法后就从**缓存文件名反推**
task_id，而缓存文件名带后缀，反推结果并不是真实 task_id：

- `note.py:815` `task_id = markdown_cache_file.stem` → 值为 `<task_id>_markdown`，
  写入状态文件 `note_results/<task_id>_markdown.status.json`（**幻影任务**）。
  实机在 `note_results/` 找到了该文件：`progress=90`、`updated_at=21:40:54`，
  而真正被前端轮询的 `<task_id>.status.json` 从 `21:40:54` 起就再也没有更新过 ——
  整个「GPT 总结」阶段（本次约 1 分多钟，视频理解时更长）前端**死卡在 90%**。
- `note.py:757` `task_id = transcript_cache_file.stem.split("_")[0]` 与
  `note.py:580` `audio_cache_file.stem.split("_")[0]` 依赖 `<uuid>_transcript.json` 的命名约定，
  一旦缓存命名规则变化就会静默写错文件。
- `_summarize_text()` 还把幻影 id 当作 `GPTSource.checkpoint_key`，checkpoint 续写/缓存
  也落在错误 key 上。

## 改动点

1. `generate()` 显式把真实 `task_id` 传给 `_summarize_text()`、`_get_transcript()`、`_transcribe_audio()`、
   `_download_media()`。
2. 三个方法签名新增 `task_id: Optional[str] = None`，删除所有 `Path.stem` 反推逻辑。
3. `task_id` 为 `None` 时保持原行为（`_update_status` 本身对空 id 直接返回，不写文件）。
4. 兼容残留幻影文件：不改写、不迁移，仅保证新任务不再产生。

## 验收

- 总结阶段每个子步骤都写入 `<task_id>.status.json`，前端不再停在 90%。
- `note_results/` 不再新增 `*_markdown.status.json` / `*_transcript.status.json`。
- 旧任务（含已存在的幻影文件）仍可被正常重试与查看。
