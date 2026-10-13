# 工单 03 · 删除分组时二选一

- **状态**：已完成
- **对应**：spec 010 §4.3

## 契约

```
POST /api/note_group/delete
{ "group_id": "g1", "delete_tasks": false }   # 默认：只删组
→ { "code": 0, "data": {"affected": 2, "deleted_tasks": [], "skipped_tasks": []} }

{ "group_id": "g1", "delete_tasks": true }    # 连组内笔记一起删
→ { "code": 0, "data": {
      "affected": 1,
      "deleted_tasks": ["t1"],
      "skipped_tasks": [{"task_id": "busy", "reason": "任务仍在执行，请等它结束或失败后再删除"}]
  } }
```

## 实现要点

- `GroupDeleteRequest` 加 `delete_tasks: bool = False`。
- `delete_tasks=True` 时对 `list_task_ids_in_group(data.group_id)` 逐个 `delete_task_completely`，
  `TaskInFlightError` → 记入 `skipped_tasks`（用户决策 `group_inflight` = 跳过进行中、其余删掉）。
- **删除动作刻意放在 `delete_group` 之前**：这样 `affected` 正好是「退回未分组」的条数。
- 两个依赖在**函数内** import（`app.db.note_group_dao.list_task_ids_in_group`、
  `app.services.task_cleanup.delete_task_completely`）—— 测试必须 patch **源模块**的属性，
  patch 路由模块的同名属性是无效的。
- **删除动作不放进 `note_group_dao`**：`db/` 层不该 import `services/`，否则依赖方向就反了。
  dao 只更新了模块 docstring 说明新的 opt-in 行为。

## 与工单 01 的分工

本工单不自己实现「删干净」，只负责「挑出要删的 id、逐个调、把跳过的记下来」。
