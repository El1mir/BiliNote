# 03 · 截图生成并发与后处理进度

- **依赖**：14（task_id 贯穿）
- **关联**：spec §4 决策 5
- **状态**：已完成

## 目标

笔记里每个 `Screenshot-mm:ss` 标记都要跑一次 `ffmpeg`（`video_helper.generate_screenshot`），
现在串行执行：标记多时后处理阶段非常慢，且前端只看到静止的「整理结果」。

## 改动点

1. `note.py::_insert_screenshots()`：先 `extract_screenshot_timestamps()` 拿到全部标记，
   用 `ThreadPoolExecutor(max_workers=min(8, cpu_count))` 并发生成截图（保序），再按原顺序替换标记。
2. 每个标记生成完成即回报 `post_processing` 进度：
   `_update_status(task_id, TaskStatus.FORMATTING, stage=POST_PROCESSING, stage_progress=..., message=...)`。
3. 单个截图失败保留原语义（返回 `None`，由调用方 `_post_process_markdown()` 捕获并告警跳过）。
4. 无标记时直接返回原文，不建线程池。

## 验收

- 截图 URL 顺序、文件名规则与改动前一致；`markdown.replace(marker, url, 1)` 语义不变。
- 多个标记时耗时明显下降，前端 post_processing 阶段有确定进度。
- 失败语义保持原样：任一张截图生成失败即整体返回 `None`（由 `_post_process_markdown` 告警跳过）。
