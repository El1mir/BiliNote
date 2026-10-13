# 工单 04 · 测试

- **状态**：已完成
- **依赖**：工单 01、02

## 交付物

`backend/tests/011-failed-task-retry/test_failed_task_retry.py`，16 个用例，6 组。

## 约定（与 spec 009/010 一致）

- **无 `conftest.py`、无 `pytest.ini`**。
- 业务错误也是 HTTP 200，断言读 body 的 `code` 字段。
- 临时 SQLite + `monkeypatch.setattr(engine_module, "SessionLocal", factory)`。

## 用例清单

| 组 | 用例 |
| --- | --- |
| ① 只有 FAILED 重试 | `test_only_failed_tasks_are_retried`、`test_missing_status_file_is_not_retried` |
| ② 原地重试 | `test_retry_reuses_task_id_and_stored_payload`、`test_retry_does_not_create_a_new_task_row`、`test_retry_writes_pending_status` |
| ③ 范围 | `test_scope_group_only_retries_that_group`、`test_scope_group_with_null_group_id_means_ungrouped`、`test_invalid_scope_is_rejected` |
| ④ 门禁 | `test_transcriber_not_ready_blocks_retry`、`test_insufficient_disk_blocks_retry`、`test_user_retry_resets_circuit_breaker` |
| ⑤ 降级 | `test_missing_payload_falls_back_to_video_id`、`test_unrebuildable_payload_is_reported_not_silently_dropped`、`test_reported_missing_task_ids`、`test_duplicate_task_ids_are_requeued_once` |
| ⑥ 路由契约 | `test_retry_route_is_registered_on_production_app` |

## 本轮踩到的坑（真实缺陷）

### `NOTE_OUTPUT_DIR` 有两个所有者 → 测试把状态文件写进仓库

- **现象**：`test_retry_writes_pending_status` 报 `AssertionError: assert 'FAILED' == 'PENDING'`（15 passed / 1 failed）。
- **根因**：`backend/app/routers/note.py:121` 的 `NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")` 是 **`str`**（`task_retry._note_output_dir()` 延迟 import 读的就是它），而 `backend/app/services/note.py:66` 的 `NOTE_OUTPUT_DIR = Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))` 是 **`Path`**，且 `NoteGenerator._update_status` 真正写 `<task_id>.status.json` 用的是**后者**。有两个独立全局量。
- **后果**：测试只 monkeypatch 了 routers 那个 → 状态文件被写进**仓库**的 `backend/note_results/`，而断言读的是 `tmp_path` 里的旧副本。
- **修法**：fixture 里 `from app.services import note as note_service` + `monkeypatch.setattr(note_service, "NOTE_OUTPUT_DIR", results_dir)`，fixture docstring 写明「两个都要重定向」。
- **清理**：删掉污染文件 `backend/note_results/failed-task.status.json`；重跑确认无新残留（`note_results/` 已被 `.gitignore:316:/backend/note_results` 忽略，无 git 污染）。
- **教训**：**模块级常量可能有多个所有者；任何写文件的新测试必须重定向所有副本，否则仓库被污染。** 这与 spec 010 的 `IMAGE_OUTPUT_DIR` 事故（`backend/tests/008-.../test_ticket02_flow.py` 往 tracked `backend/static/screenshots/` 写真实文件）是同一类错误的第二次出现。

### pi-lens 的 `BaseRoute` 属性报错

`test_retry_route_is_registered_on_production_app` 原本用集合推导式访问 `route.path` / `route.methods`，静态检查报 `Cannot access attribute "path"/"methods" for class "BaseRoute"`。改成 `getattr` 循环：

```python
paths = set()
for route in app.routes:
    if "POST" not in (getattr(route, "methods", None) or set()):
        continue
    path = getattr(route, "path", None)
    if path:
        paths.add(path)
assert "/api/retry_failed_tasks" in paths
```

## 验证

- `cd backend; .venv\Scripts\python.exe -m pytest tests/011-failed-task-retry -q` → **16 passed, 1 warning in 5.05s**
- `cd backend; .venv\Scripts\python.exe -m pytest tests -q` → **619 passed, 2 warnings, 13 subtests passed in 61.72s**（基线 603，+16）
- `backend/tests/011-failed-task-retry/test_failed_task_retry.py:20` 的 `Import "pytest" could not be resolved` 已 `lens_diagnostic_mark` 为 **false-positive**（pytest 在 `backend/.venv`，LSP 对该目录不做 venv 解析；仓库内所有既有测试文件同一写法）
