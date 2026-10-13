# 03 · 删除「重新生成」与失败重试

- **状态**：已实现
- **依赖**：无
- **上游 spec**：`specs/008-ocr-assist-and-legacy-cleanup/spec.md` §7

## 目标

彻底移除「复用已有 `task_id` 重跑」这一整条链路，包括把它当作「重新生成」用的 UI，也包括把它当作「失败重试」用的按钮。用户已明确要求连失败重试按钮一起删。

移除后，**生成笔记永远是新建任务**。

## 为什么必须一起删

「重新生成」和「失败重试」共用同一套机制，只是入口不同：

- 后端同一个 `if data.task_id:` 分支
- 前端同一个 `retryTask`
- 同一个 `_is_task_id_in_flight` 并发保护

只删其一必然留下另一条的入口，或者留下无法解释的死代码。所以本 ticket 的删除是**成对**的。

## 现状锚点

前端：

- `BillNote_frontend/src/pages/HomePage/components/NoteForm.tsx:316` —— 全仓库唯一一处 `'重新生成'` 字面量：
  `const label = generating ? '正在生成…' : editing ? '重新生成' : '生成笔记'`
- `NoteForm.tsx:180` `const editing = currentTask && currentTask.id`
- `NoteForm.tsx:254-264` 提交时 `task_id: currentTaskId || ''`，且 `if (currentTaskId) { retryTask(currentTaskId, payload); return }`
- `NoteForm.tsx:322` 宽度类名依赖 `editing`；`:332-337` `新建笔记` 按钮；`:291-295` `handleCreateNew` → `setCurrentTask(null)`
- `NoteForm.tsx:403,439,442` `disabled={!!editing}` 锁死表单
- `BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx:425-439` 失败重试按钮，标签 `重试` 在 `:433-435`
- `BillNote_frontend/src/store/taskStore/index.ts:112,217-259` `retryTask`

后端：

- `backend/app/routers/note.py:68` `VideoRequest.task_id`
- `backend/app/routers/note.py:406-421` 复用分支（日志 `重试模式，复用已有 task_id=`）
- `backend/app/routers/note.py:391-396` 无 `task_id` 时的按视频去重
- `backend/app/routers/note.py:166-181` `_is_task_id_in_flight`

## 任务

### 前端

1. 删除 `editing` 概念及其全部派生使用：`disabled` 锁定、标签三元、宽度类名、`新建笔记` 按钮、`handleCreateNew`。
2. 删除提交时的 `currentTaskId` 短路分支；提交永远走新建。
3. 删除 `MarkdownViewer.tsx` 的失败重试按钮，以及 store 的 `retryTask`。
4. **表单解锁是重点**：删除 `editing` 后必须确认用户仍然能正常修改 URL、平台、本地路径等表单字段。这是删除后最容易回归的功能点。
5. 检查删除后 `setCurrentTask` / `getCurrentTask` 是否仍被使用；若仅服务于这两个功能则一并清理，仍被用于「查看历史任务」则保留。

### 后端

1. 删除 `VideoRequest.task_id` 字段与复用分支；`task_id` 一律由服务端 `str(uuid.uuid4())` 生成。
2. 删除 `_is_task_id_in_flight`（其唯一用途是保护复用路径）。
3. `_is_task_in_flight`（按 video_id + platform 去重）**是否保留需要显式决策**：它保护的是「同一视频并发发起」而不是重试。建议保留，但要在代码注释与 spec 中写清它现在的语义只剩并发保护。
4. 注意 `backend/app/routers/note.py:398-405` 有一段被注释掉的「笔记已生成，请勿重复发起」去重。删除重试后，若期望「已生成过的视频再点生成」的行为明确化，需在此处显式决策（重新启用 / 保持允许 / 改为提示），不要留着注释死代码。

### 需要留意的连带影响

- `_execute_note_with_retry`（`backend/app/routers/note.py:225-252`）与 `NOTE_MAX_RETRIES` / `NOTE_RETRY_BACKOFF`（`:116-118`）是**自动重试**，与本次删除**无关**，不要误删。
- 浏览器扩展不受影响：`BillNote_extension/src/background/main.ts:77-114` 从不提交 `task_id`。建议加一条 grep 断言防止回归。

## 验收

- 全仓库 `grep -rn "重新生成"` 无结果。
- 全仓库 `grep -rn "retryTask"` 无结果（`BillNote_extension` 若有同名概念需人工确认，当前审计为无）。
- 后端 `task_id` 不再作为请求字段存在。
- 表单在选中一个历史任务后仍可自由修改 URL 并提交，提交产生**新任务**。
- 失败的任务在 UI 上不再提供「重试」按钮；失败状态有明确展示。
- 后端测试、前端测试、生产构建通过。
