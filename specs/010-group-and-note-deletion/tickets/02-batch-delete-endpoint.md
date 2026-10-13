# 工单 02 · 批量删除端点 `POST /delete_task_records`

- **状态**：已完成
- **对应**：spec 010 §4.4

## 契约

```
POST /api/delete_task_records
{ "task_ids": ["a", "b"] }
→ { "code": 0, "data": {
      "deleted": ["a"],                                   # task_id 字符串列表（已展平）
      "failed": [{"task_id": "b", "error": "任务仍在执行，请等它结束或失败后再删除"}],
      "removed_rows": 1,
      "files": ["a.status.json", "a.json"]
  } }
```

## 规则

- 空列表 → `code=400`；`len > MAX_BATCH_DELETE = 1000` → `code=400`。
- `seen` 字典**去重保序**：用户的选择顺序就是删除顺序，结果列表要能对得上。
- **逐条隔离**：一条失败不影响其余。三种失败来源分别记入 `failed`：
  `_valid_task_id` 不过（「任务标识无效」）、`TaskInFlightError`（`str(exc)`）、其他异常（warning + `str(exc)`）。
  批量接口最怕「重试一次还是全挂」。
- `_TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")` —— task_id 会直接拼进文件名，
  路径分隔符与超长串必须挡在路由层。

## 注意

`deleted` 是 **task_id 字符串列表**，不是 `{task_id, removed, files}` 字典列表
（`backend/app/routers/note.py:1849` 用 `[item["task_id"] for item in deleted]` 展平了）。
前端只需要知道哪些成了；`removed_rows` 与 `files` 是给观测/测试用的。
