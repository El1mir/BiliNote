# 工单 02 · `POST /api/retry_failed_tasks` 端点

- **状态**：已完成
- **依赖**：工单 01

## 交付物

在 `backend/app/routers/note.py` 末尾追加端点（不改动既有端点）。

## 契约

```http
POST /api/retry_failed_tasks
{ "scope": "all" | "group", "group_id": "..." | null }

200 { "code": 0, "msg": "...", "data": {
      "scope", "group_id", "candidates", "requeued", "skipped", "missing" } }
```

## 验收清单

- [x] `class RetryFailedRequest(BaseModel): scope: str = "all"; group_id: Optional[str] = None`
- [x] `scope` 只接受 `{"all","group"}`，否则 `code=400`
- [x] 门禁顺序与 `/generate_notes` 一致：就绪门禁 `code=300102` / `reason=transcriber_model_not_ready` → 磁盘门禁 `code=300104` / `reason=insufficient_disk_space`
- [x] `_get_circuit_breaker().reset()` —— 用户主动重试就是熔断复位信号
- [x] `scope == "all"` → `retry_failed_tasks(None)`；否则 `list_task_ids_in_group(data.group_id)` 后 `retry_failed_tasks(ids)`
- [x] `scope == "group"` + `group_id: null` = **未分组**（`list_task_ids_in_group(None)`），不是「全部」—— 传错会误伤别的组
- [x] 异常 → `code=500`
- [x] 路由真的挂在生产 app 上（测试自建 `FastAPI()` + `include_router` 会让测试全绿而生产 404）

## 验证

- `from app import create_app; create_app(contextlib.nullcontext)` 列路由 → `POST /api/retry_failed_tasks` 在册
- `backend/tests/011-failed-task-retry/test_failed_task_retry.py::test_retry_route_is_registered_on_production_app` 通过
