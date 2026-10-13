# 工单 01 · 唯一的删除实现 `services/task_cleanup.py`

- **状态**：已完成
- **对应**：spec 010 §4.1、§4.2

## 为什么

`delete_task_record` 里内联着一份「什么算删干净」。spec 010 要「删除分组时连组内笔记一起删」——
再抄一份就会出现两个会各自漂移的判定。`utils/video_reader.py` 的 Windows `os.rename` 缺陷
正是「读路径与写路径各有一份有效性判定、两份都错」造成的。所以先收敛，再加功能。

## 做了什么

新建 `backend/app/services/task_cleanup.py`：

- `TASK_ARTIFACT_SUFFIXES = (".json", ".status.json", "_transcript.json", "_audio.json", ".gpt.checkpoint.json")`
- `FINISHED_STATUSES = frozenset({TaskStatus.SUCCESS.value, TaskStatus.FAILED.value})`
- `class TaskInFlightError(Exception)`
- `_output_dir() -> Path` —— **延迟** import `app.routers.note` 再读 `NOTE_OUTPUT_DIR`，
  让测试的 `monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp)` 生效
- `read_task_status(task_id) -> Optional[str]` —— 文件不存在/损坏/非 dict/status 为空 → `None`
- `_delete_artifacts(task_id) -> List[str]` —— 单个文件删不掉只 `logger.warning`，不让整次删除失败
- `delete_task_completely(task_id, *, allow_in_flight=False) -> Dict[str, Any]`
  返回 `{"task_id", "removed", "files"}`；空 id 抛 `ValueError`

运行登记表（进行中守卫的第一信号）：

- `_RUNNING_TASKS: set` + `_RUNNING_LOCK = threading.Lock()`
- `mark_task_running(task_id: Optional[str])` / `unmark_task_running(task_id: Optional[str])`
- `is_task_running(task_id: Optional[str]) -> bool` / `running_task_ids() -> frozenset`
- `clear_running_tasks()` —— **仅供测试**，进程级状态不该跨用例泄漏

`is_task_in_flight(task_id)` = 运行登记表命中 **或**（状态文件存在且非终态）。

## 关键取舍

- **签名放宽到 `Optional[str]`。** 实现里本来就有 `if not text: return` 的空值守卫，
  签名却写着 `str` —— 守卫就成了一句空话。
- **刻意不用「DB 行存在」兜底。** 容量边界会把 `note_output` 整个纳入清理候选
  （`media_resource_service.py:743-770`），状态文件可能先于 DB 行消失。那种任务在列表里
  显示成「等待中」，若被判成进行中就会**永远删不掉**，而前端没有别的出口 —— 死路。

## 接线

- `backend/app/routers/note.py` 的 `delete_task_record` 改为调 `delete_task_completely`，
  `TaskInFlightError` → `R.error(str(exc), code=CODE_TASK_IN_FLIGHT)`（`300106`）。
- 新增 `_run_note_task_guarded(task_kwargs)`（`mark` → `run_note_task(**kwargs)` → `finally: unmark`）。
  用**模块全局**查 `run_note_task`，所以测试的 monkeypatch 仍生效。
- `_dispatch_note_task` 改为「**入队即 mark**」；`submit` 抛异常时先 `unmark` 再 `logger.error`。
- 单条路径 `/generate_note` 也改走 `_run_note_task_guarded`。
