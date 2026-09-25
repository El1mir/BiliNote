# 05 · 前端：采样方式下拉 + 联动

- **依赖**：04
- **关联**：spec §4.2
- **状态**：✅ 已完成

## 改动点
1. `NoteForm` schema / defaultValues / form.reset 新增 `sampling_mode`、`max_frames`；
2. 视频理解区域新增「采样方式」下拉（间隔采样 / 高价值帧采样）；
3. `sampling_mode === 'smart'` 时显示「最大帧数」，否则显示「采样间隔（秒）」；
4. 生成 payload 透传 `sampling_mode` / `max_frames`。

## 验收
- 下拉切换时对应参数输入框切换；
- 视频理解未启用时下拉禁用。
