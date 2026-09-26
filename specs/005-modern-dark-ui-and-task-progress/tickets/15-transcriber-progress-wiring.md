# 15 · 转写进度回调接线与阶段明细

- **依赖**：13、14
- **关联**：spec §5（ticket 04 的补漏）
- **状态**：已完成
- **日期**：2026-09-26（实机排查 BV1E7wtzaEdq 任务时发现）

## 背景

`note.py:773-778` 先调用 `self.transcriber.transcript(file_path=audio_file)`，
**之后**才 `setattr(self.transcriber, "progress_callback", ...)`：

```python
transcript = self.transcriber.transcript(file_path=audio_file)   # 这里回调还是 None
setattr(self.transcriber, "progress_callback", self._transcriber_progress_callback(task_id))
```

结果整个转写过程（本次 80 段 / 138.69 秒）阶段进度永远不动，前端只能看到静止的
「音频转写」——ticket 04 声称的转写进度埋点实际上从未生效。

同理，`SUMMARIZING` 与 `SAVING` 只写一次状态、不带 `detail`，
长阶段无法区分「在总结」和「已经卡死」。

## 改动点

1. `_transcribe_audio()` 在调用 `transcript()` **之前**安装 `progress_callback`，
   调用结束后用 `getattr`/`delattr` 复原（避免污染单例转写器的后续任务）。
2. `_summarize_text()` 写 `SUMMARIZING` 时带 `message` 与 `detail`（模型名、转写段数、是否有配图）。
3. `SAVING` 阶段补充 `message`/`detail`，明确「结果文件 → 数据库 → 状态文件」的进度语义。
4. 保持 `_update_status` 的写入协议不变（前端字段无需改动）。

## 验收

- 用 OpenAI 兼容 ASR（chat 风格）跑长音频时，`stage_progress` 随段数递增，
  `message` 显示「正在转写第 i/n 段」。
- 转写结束后回调被清理，下一个任务不会复用上一个任务的 task_id。
- `SUMMARIZING` / `SAVING` 阶段前端可见具体 message，而不是空白。
