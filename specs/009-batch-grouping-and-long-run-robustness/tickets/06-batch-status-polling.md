# 06 · 前端批量状态端点与轮询改造、批量 >200 二次确认

- **依赖**：无
- **关联**：spec §4 决策 13–15、§5、§6
- **状态**：已完成

## 目标

200 个待办任务时，前端每轮轮询只发 1 个状态请求，且不会把仍在运行的任务误标为失败。

## 背景

`BillNote_frontend/src/hooks/useTaskPolling.ts:86-90` 是 N+1 **串行**轮询：200 个待办每 3 秒发 200 个顺序 `GET /task_status`（≈67 req/s）。叠加 `GET /task_list` 每次调用做 400 次 JSON 读（`backend/app/routers/note.py:1175-1176`）与单进程 uvicorn，30s axios 超时（`BillNote_frontend/src/utils/request.ts:29`）触发后 `MAX_POLL_FAILURES = 5`（`useTaskPolling.ts:67,129-132`）会把**还在跑**的任务在客户端误标 FAILED —— 代码注释里已警告过「误标失败 + 重复提交」。

## 改动点

1. 后端新增 `POST /api/task_status/batch`：
   - 请求 `{task_ids: string[]}`，返回每个 id 的**轻量**状态（`status/stage/stage_label/progress/stage_progress/message/updated_at`）；
   - **不含** markdown 与 transcript（对比 `get_task_status`（`routers/note.py:1036-1049`）成功时每次重发整份内容）；
   - 未知 id 返回 `null` 而不是报错；
   - 用 `POST`（200 个 task_id 拼进 GET query 会超长）。
2. 前端 `useTaskPolling.ts:86-90`：改为每轮**一次**批量调用，再按 id 分发结果；`get_task_status` 仍保留给单任务详情使用。
3. `get_task_status` 成功时不再每次重发整份 markdown+transcript（按需加载），避免 200 个任务同时把大 JSON 拉进内存。
4. 失败判定收紧：单轮请求失败不应把任务标 FAILED；只在「批量端点本身连续失败」时提示，不改变任务状态（避免误标）。
5. `BillNote_frontend/src/pages/HomePage/components/BatchImportDialog.tsx:158-166`：条目数 > 200 时弹**二次确认**，提示预估磁盘占用与时长；不设硬上限。

## 验收

- 200 个待办任务时每轮轮询只发 1 个状态请求。
- 仍在运行的任务不会被客户端误标为 FAILED。
- 单任务详情页仍能拿到完整 markdown。
- 批量条目 > 200 时出现二次确认；确认后可正常提交。

## 测试

- 后端：`test_task_status_batch.py` —— 混合存在/不存在的 task_id，断言存在项返回轻量字段、缺失项为 `null`、响应体不含 markdown。
- 前端：现有前端测试若覆盖 `useTaskPolling`，需同步更新为单次调用断言。
