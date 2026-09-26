# 06 · 并发正确性测试与实测对比

- **依赖**：01、02、03、04、05
- **关联**：spec §6
- **状态**：已完成

## 测试（backend/tests/006-note-pipeline-performance/）

| 文件 | 覆盖 |
|---|---|
| `test_asr_chunk_concurrency.py` | 并发转写：结果顺序与串行一致；`chunk_concurrency=1` 退化串行；单段失败仍抛出；并发下每分钟请求数不超过 `max_rpm` |
| `test_video_reader_parallel.py` | 并发拼图 + 编码：合成图片下 `video_img_urls` 数量/顺序与串行一致；并发度 1 与 8 结果相同；进度回调单位数等于网格数+图像数 |
| `test_screenshot_concurrency.py` | `_insert_screenshots` 并发：marker 替换顺序/URL 顺序不变；单标记失败仅跳过该标记；进度回调次数等于标记数 |
| `test_downloader_skip_download.py` | `BilibiliDownloader.download(skip_download=True)` 不调用媒体下载（monkeypatch yt-dlp），`ext=None` 不拼出 `xxx.None` |
| `test_local_audio_from_video.py` | 本地已有视频时不再发起音频网络下载，走 ffmpeg 抽音频；抽音频失败回退网络下载 |
| `test_vector_index_offthread.py` | `run_note_task` 提交后台索引；索引抛错不影响任务 `SUCCESS` |

## 实测对比（backend/logs/app.log + 状态文件时间戳）

基准：2026-09-26 的 BV1E7wtzaEdq（80 段 ASR / 45 组网格 / 400 帧 / 含视频理解）。

| 指标 | 改动前 | 改动后 |
|---|---|---|
| 转写耗时 | 138.69s（80 段串行） | 本次未采集真实视频基准；并发路径由自动化测试验证 |
| 拼图 + base64 | 数分钟且无进度 | 本次未采集真实视频基准；并发、顺序与进度由自动化测试验证 |
| 媒体下载次数 | 2（视频 + 音频） | 代码路径已支持本地视频抽音频；未用真实视频重新计数 |
| 向量索引在关键路径 | 是（+2s） | 否；后台线程池测试通过 |

> 说明：本次完成了功能与回归验证；真实视频的前后耗时数据需在目标机器上单独采集后再补录。

## 验收

- `cd backend && .venv\Scripts\python.exe -m pytest tests/006-note-pipeline-performance -q` 全绿。
- 既有测试不做功能删改，`tests/001-*` ~ `tests/005-*` 全部通过。
