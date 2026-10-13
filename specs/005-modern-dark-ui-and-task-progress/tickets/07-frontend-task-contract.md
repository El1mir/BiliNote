# 07 · 前端任务类型、轮询和持久化适配

- **依赖**：02
- **关联**：spec §5；001
- **状态**：已完成

## 目标

让前端任务模型完整保存后端阶段字段，并兼容已有 local/persist 任务数据。

## 改动点

1. 扩展 Task 类型：stage、stageLabel、progress、stageProgress、message、detail、updatedAt。
2. 轮询成功时合并全部阶段字段，而不只更新旧 status。
3. 保留连续轮询失败保护，避免网络抖动误判任务失败。
4. 旧任务缺少新字段时使用兼容默认值。
5. 清理终态任务的轮询计数和临时状态。

## 验收

- 刷新页面后任务阶段、详情和进度仍能恢复。
- 状态字段为未知值时 UI 不崩溃，有通用回退展示。
- 多任务轮询互不覆盖阶段信息。

## 完成情况（2026-10-05 核查）

三条验收都有对应实现，逐条落点如下。

- **扩展 Task 类型**：`BillNote_frontend/src/store/taskStore/index.ts:40-52`（`TaskStage` 14 值）、
  `:54-62`（`TaskProgress`）、`:124-130`（`Task` 含 `stage`/`stageLabel`/`progress`/`stageProgress`/`message`/`detail`/`updatedAt`）。
- **轮询合并全部阶段字段**：`BillNote_frontend/src/hooks/useTaskPolling.ts:12-21`
  （`normalizeTaskStatus` 同时吃 snake_case 与 camelCase）、`:91-123` 逐任务写入。
  `taskStore/index.ts:260-272` 的 `mergeServerRow` 明确**不降级**已有阶段信息。
- **连续失败保护**：`useTaskPolling.ts:44-45`（`failuresRef` + `MAX_POLL_FAILURES = 5`）、
  `:76` 成功即重置、`:82-84` 只在第 5 次才 toast。**单次失败绝不把任务标成 FAILED。**
- **旧任务兼容默认值**：`taskStore/index.ts:216-219`（`stage:'queued'` / `stageLabel:'等待处理'` /
  `progress:0` / `stageProgress:0`）、`:347-394` 的 `rehydrateTask` 还兼容把进度嵌在 `raw.progress` 里的旧形状。
- **未知状态回退**：`ProgressTimeline.tsx:67` 未知状态回退 `'queued'`。
- **终态清理**：`useTaskPolling.ts:54-59` 终态任务不再进入 pendingTasks。

### 一处已知残留（已归入工单 08）

`taskStore/index.ts:129` 把 `detail` 声明成 `string | null`，而后端写入的 `detail` 是 dict
（`backend/app/services/note.py:1446` 的 `detail or {}`）。类型与实现不符，且
`utils/text.ts:12-20` 的 `asText` 对普通对象返回 `''` —— 于是 `detail` 永远不显示。
这是工单 08 的第一个缺陷，不在这里修。
