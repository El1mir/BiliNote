# 工单 01 · 重试服务 `task_retry.py`

- **状态**：已完成
- **依赖**：无（spec 009 的 `payload_json` 列已就位）

## 交付物

新建 `backend/app/services/task_retry.py`，提供把失败任务**原地**重新排队的能力。

## 验收清单

- [x] `FAILED_STATUS = "FAILED"`、`IN_FLIGHT_STATUSES`（7 个在途状态）、`PAYLOAD_KEYS`（19 键，与 `routers/note.py` 的 `_build_task_kwargs` 去掉 `task_id` 一致）
- [x] `_note_output_dir()` **延迟** import `app.routers.note` 读 `NOTE_OUTPUT_DIR`（这样测试的 monkeypatch 才生效，理由同 `services/task_cleanup.py` 的 `_output_dir`）
- [x] `read_task_status(task_id) -> Optional[str]`：文件不存在 / 损坏 / 非 dict / status 为空 → `None`
- [x] `payload_from_row(row) -> Optional[dict]`：按 `PAYLOAD_KEYS` 白名单过滤；`task_id` / `platform` 以 DB 为准，不让 payload 里的旧值覆盖
- [x] `_fallback_payload(video_id, platform)`：`payload_json` 缺失时按 `video_id` 重建 bilibili URL；`_fallback_payload` 的 `_p<N>` 后缀解析**刻意不与 `task_recovery.py` 复用**（恢复要尽量救活、重试要尽量不误导，策略会各自演化）
- [x] `_select_retryable(rows)` 三分类并给出跳过原因；SUCCESS 与任何未知状态都不猜
- [x] `retry_failed_tasks(task_ids=None) -> {"candidates","requeued","skipped","missing"}`；去重保序；`task_ids=None` 走 `list_recoverable_tasks()`（整库），否则逐个 `get_video_task`，查不到的进 `missing`
- [x] 每条先 `NoteGenerator()._update_status(task_id, TaskStatus.PENDING, message="用户手动重试")`，再 `_dispatch_note_task(task_kwargs)`
- [x] 参数还原失败 → 跳过，原因「缺少可用的生成参数（创建时未存参数，且无法按视频号重建）」

## 实现中修掉的两个真实缺陷

1. **`missing` 可能未绑定**：首版把 `missing = []` 写在 `else:` 分支内，后面跟着一个死占位符 `if wanted is not None: pass`。`task_ids=None`（整库）时 `stats["missing"]` 引用的就是未绑定名。修法：`missing: List[str] = []` 提到 `if wanted is None:` 之前，`stats["missing"] = missing` 无条件使用。**教训：`if <cond>: pass` 占位符往往是分支作用域绑定已经出错的信号。**
2. **`?p=0` 无效地址**：原用 `tail.isdigit()` 守卫 `int(tail)`，但 `isdigit()` 只说明「全是数字字符」，`"00"` 能通过并拼出 `?p=0`。改成 `try: parsed = int(tail) / except ValueError: parsed = 0` 并加 `parsed > 0` 判断。

## 验证

- `ast.parse` OK；`from app.services import task_retry` IMPORT OK；`PAYLOAD_KEYS` 长度 19。
- `cd backend; .venv\Scripts\python.exe -m pytest tests/011-failed-task-retry -q` → 16 passed。
- `lens_diagnostics mode=full paths=["backend/app/services/task_retry.py"]` → **0 blocking**（残留 14 条 `UP006`/`UP007` 风格告警：`typing.List`/`Dict` 建议改内建泛型，与仓库既有风格一致，不改）。
