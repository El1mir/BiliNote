# 10 · 日志降噪：截图 ffmpeg 与调试 print

- **依赖**：无
- **关联**：spec §12 决策 #2（ffmpeg 静音，扩展到截图/下载路径）
- **状态**：✅ 已完成

## 现象
开启「截图」格式时，每张截图都打印一行 `Running command: ['ffmpeg', ...]`，
一个视频 170+ 张截图 → 刷屏；`video_reader` / `bilibili_downloader` 也有调试 `print`。

## 改动点
1. `app/utils/video_helper.py`
   - ffmpeg 命令加 `-hide_banner -loglevel error -nostats`，`-y` 移到输出参数之前；
   - `print("Running command:")` → `logger.debug`；
   - `print("ffmpeg failed:")` → `logger.error`。
2. `app/utils/video_reader.py`：删除 5 处目录调试 `print`。
3. `app/downloaders/bilibili_downloader.py`：`print("video_url", ...)` → `logger.debug`。

## 追加（2026-09-26）：去重探测日志降噪
4. `app/db/video_task_dao.get_task_by_video()`：命中 / 未命中原来都是 `logger.info`，
   批量展开时每个分P探测一次 → 49 个视频刷 49 行 `No task found for video_id ...`。
   降为 `logger.debug`（去重标记功能不变）。

## 验收
- 截图流程不再打印命令；截图仍能正常生成（实测 437KB jpg）；
- 抽帧/下载不再有调试 print；
- 展开大合集时不再刷 `No task found for video_id ...`。
