# 工单 04 · 前端多选删除与分组删除选项

- **状态**：已完成
- **对应**：spec 010 §4.5

## 改动

**`BillNote_frontend/src/utils/taskStatus.ts`（新增）**
`FINISHED_TASK_STATUSES = ['SUCCESS','FAILED'] as const`；`isTaskInFlight(status)`。
文档串写明「真正的判定在后端，前端这份只用来把明显删不掉的入口置灰」。

**`src/services/note.ts`**：`interface BatchDeleteResult` + `deleteTaskRecords(task_ids)`。
**`src/services/noteGroup.ts`**：`interface GroupDeleteResult` + `deleteNoteGroup(groupId, deleteTasks = false)`。
**`src/store/taskStore/index.ts`**：新增 `removeTasks(ids): Promise<BatchDeleteResult | null>` ——
乐观删除本地状态，**整批一次请求**（1000 条逐条请求会把浏览器连接池和 SQLite 写锁一起打满）。

**`NoteHistory.tsx`**
- 复选框条件从 `task.status === 'SUCCESS' && onSelectionChange` 改为 `onSelectionChange`
  （用户决策 `checkbox_scope` = 放开到全部任务），label 改为中性的「选中」。
- 单条删除加 `disabled={isTaskInFlight(task.status)}`，Tooltip `'生成中，暂不能删除'` / `'删除'`。
- `renderTask` 是**直接返回 JSX 的箭头函数**（不是块体），所以改动一律用行内表达式，
  避免为了加一个局部变量而重构整段。

**`History.tsx`**
- 删掉 `completedIds`；新增 `allVisibleSelected`（**全选只覆盖当前可见任务** ——
  选中看不见的笔记再删是最容易误伤的操作）。
- `confirmDeleteGroup` 改为 `deleteNoteGroup(group.id, alsoDeleteTasks)`，按 `delete_tasks`
  分两支汇报（`delete_tasks=True` 时汇报 `deleted_tasks.length` 与 `skipped_tasks.length`，
  跳过项明确说「已移入未分组」）。
- 新增 `deleteSelected`：调 `removeTasks`，**如实汇报失败条目**
  （`failed` 非空时 `toast.error`）。批量删除最忌讳「看起来成功了，其实有几条没删」。
- 工具条加 destructive「删除选中」按钮；全选标签改为 `全选 (N)`，`onChange` 用 `visibleTasks`。
- 删除分组弹窗加红色警示复选框「同时删除组内的全部笔记（不可恢复；生成中的笔记会被保留并移入未分组）」，
  `DialogDescription` 随勾选切换，`onOpenChange` 关闭时重置为未勾选（避免下次误删）。

## 关键取舍

**前端不在本地过滤进行中的任务**：选中的 id 全部发给后端，由后端逐条返回 `deleted`/`failed`。
两边各判一次必然会漂移，而漂移的表现就是「点了删除但什么也没发生」—— 用户最没法排查的那种。
`isTaskInFlight` 只用于置灰单条删除按钮。
