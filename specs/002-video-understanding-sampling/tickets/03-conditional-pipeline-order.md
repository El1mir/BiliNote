# 03 · 后端：按需调整抽帧时序

- **依赖**：02
- **关联**：spec §3-3（Q3 决议）
- **状态**：✅ 已完成

## 目标
`smart` 需要字幕分段，因此抽帧延后到转写之后；`interval` 不需要，保持原顺序。

## 改动点
1. `NoteGenerator.generate()` 新增 `sampling_mode` / `max_frames` 参数；
2. `_download_media()` 新增 `sampling_mode`：`interval` 时照常抽帧，`smart` 时只下视频、抽帧延后；
3. `generate()` 在转写完成后，若 `smart` + `video_understanding` 再构造 `VideoReader` 抽帧，字幕边界取自 `transcript.segments[*].start`。

## 验收
- `interval` 流程与改动前一致（下载阶段抽帧）；
- `smart` 在转写后抽帧，字幕分段数写入日志；
- 失败会抛出并标记任务失败。
