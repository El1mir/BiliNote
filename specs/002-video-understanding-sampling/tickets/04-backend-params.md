# 04 · 后端：`sampling_mode` / `max_frames` 透传

- **依赖**：03
- **关联**：spec §4.1
- **状态**：✅ 已完成

## 改动点
1. `VideoRequest` 与 `BatchGenerateRequest` 新增 `sampling_mode`（默认 `interval`）/ `max_frames`（默认 60）；
2. `run_note_task` 新增同名参数并透传给 `NoteGenerator.generate`；
3. `POST /api/generate_note` 与 `POST /api/generate_notes` 的入队调用同步传参。

## 验收
- 单条与批量两条路径都能把采样配置带到生成流程；
- 不传时行为与旧版一致（`interval`）。
