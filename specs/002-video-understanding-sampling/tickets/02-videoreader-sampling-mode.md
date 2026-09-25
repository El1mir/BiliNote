# 02 · 后端：VideoReader 采样模式分派

- **依赖**：01
- **关联**：spec §3-1、§3-3
- **状态**：✅ 已完成

## 目标
`VideoReader` 支持 `interval` / `smart` 两种抽帧方式，拼图流程不变。

## 改动点
1. `VideoReader.__init__` 新增 `sampling_mode` / `max_frames` / `subtitle_starts`；
2. `extract_frames(timestamps=None)` 支持外部传入时间点；
3. `run()`：`smart` → 调 `select_smart_timestamps()`，`interval` → 原固定间隔逻辑。

## 验收
- `smart` 模式调用采样器并透传字幕时间点；
- `interval` 模式不调用采样器；
- 两模式都能正常拼图。

## 测试
`backend/tests/002-video-understanding-sampling/test_video_reader_sampling.py`
