# 01 · 批量分组：上限与报错、延后建组、前端必填与归属

- **依赖**：无
- **关联**：spec §4 决策 1–5、§6
- **状态**：已完成

## 目标

每次批量提交都落到一个新建的组；批量任务在提交瞬间就在前端显示为已归组；组数上限不再静默退化为未分组。

## 改动点

1. `backend/app/db/note_group_dao.py:36`：`MAX_GROUPS` 200 → **1000**。
2. `backend/app/routers/note.py:467-487` `_resolve_batch_group`：建组失败（含 `NoteGroupError` 超限）**不再 `return ""`**，改为向上抛出/返回可辨识的失败，由 `generate_notes` 转成明确错误响应。空名分支保留（前端已保证必填，后端仍需兜底语义明确）。
3. `backend/app/routers/note.py:768-861` `generate_notes`：**延后建组** —— 先把整批过完 `_is_generated_task` / `_is_task_in_flight` 判定，收集真正要入队的条目；**只有确实至少一条**时才 `create_group`，再逐条 `_enqueue_task(..., group_id)`。全被跳过时不建组（响应里 `group_id` 为 `null`）。
4. `BillNote_frontend/src/pages/HomePage/components/BatchImportDialog.tsx:236-244`：组名输入框改**必填**，为空时禁用提交按钮并给出提示；提交 payload（`:192`）不再发 `group_name: undefined`。
5. `BillNote_frontend/src/store/taskStore/index.ts:294-302` `addPendingTask`：增加 `groupId` 参数并写入；`BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx:360-372` `handleBatchSubmitted` 用响应里的 `group_id` 传入，不再只传 `groupName`。
6. 前端读取 `generate_notes` 响应里的 `group_id` 时同步修正本地 `groupName`（组名以后端为准）。

## 验收

- 连续两次批量 → 两个不同的组，成员各自正确。
- 组名留空时无法提交。
- 提交后任务立刻出现在正确的组里（不等 `loadTasks`）。
- 整批都被去重/在途跳过 → 不产生空组。
- 组数达上限 → 明确报错，不落未分组。

## 测试

- `backend/tests/009-batch-grouping-and-long-run-robustness/test_batch_grouping.py`（新增）：
  - 两次批量得到两个不同 group_id；
  - 全跳过时不建组；
  - 达到 `MAX_GROUPS` 时返回明确错误码而非未分组；
  - `group_id` 出现在响应里。
- 现有 `backend/tests/001-bilibili-batch-import/test_batch_generate_api.py` 目前**完全不覆盖** `group_name` 建组路径，需在此补一条回归用例。
- 注意 `backend/tests/007-note-archive-and-media-cache/test_note_group_api.py:277` 锁死了「删组不删任务」，改动不得破坏它。
