# 07 · 前端：批量提交与任务列表

- **依赖**：03 / 06
- **关联**：spec §5.2 / §8

## 目标

把勾选结果提交到批量端点，并把返回的任务批量加入任务列表。

## 改动点

1. `note.ts` 新增 `generateNotes(payload)`。
2. 弹窗「生成」按钮：组装 `items`，沿用当前表单的 model/provider/style 等参数。
3. 返回 `task_id[]` → 批量 `addPendingTask` 到 `taskStore`。
4. 任务列表展示：按来源分组或加来源标签（spec 待确认 #6）。
5. 逐条轮询状态（复用 `useTaskPolling`）。

## 验收

- 提交后任务列表出现对应数量的条目；
- `skipped` 条目不建任务、有提示；
- `failed` 条目标红并可手动重试；
- 参数与单视频流程一致。
