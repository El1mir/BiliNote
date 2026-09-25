# 08 · 并发隔离：VideoReader 实例级目录 + 清理 + ffmpeg 静音

- **依赖**：05（并发默认值 5）
- **关联**：spec §12
- **状态**：✅ 已完成

## 目标

消除并发任务互相清空抽帧/缩略图目录，以及 ffmpeg 刷屏。

## 改动点

1. `backend/app/utils/video_reader.py`
   - `__init__`：`frame_dir` / `grid_dir` 未显式传入时，使用唯一 token 子目录
     `data/output_frames/<uuid12>`、`data/grid_output/<uuid12>`；
   - 记录 `_owns_frame_dir` / `_owns_grid_dir`，外部传入的目录不清理；
   - `run()` 增加 `finally: self._cleanup_temp_dirs()`，任务结束 `rmtree` 自己的目录；
   - `ffmpeg.probe(..., loglevel="quiet")`；抽帧命令 `-loglevel quiet`。

## 验收

- 两个 `VideoReader` 实例的 `frame_dir` / `grid_dir` 不相等；
- `_cleanup_temp_dirs()` 删除自动目录、保留显式传入目录；
- 抽帧日志不再出现 `libdav1d` 刷屏。

## 测试

`backend/tests/001-bilibili-batch-import/test_video_reader_isolation.py`
