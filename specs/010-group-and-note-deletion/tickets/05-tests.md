# 工单 05 · 测试

- **状态**：已完成
- **对应**：spec 010 §7

## 落点

`backend/tests/010-group-and-note-deletion/test_task_cleanup.py` —— **24 passed**。

约定沿用 spec 009 ticket 08：不引入 `conftest.py`；业务错误码仍是 HTTP 200 + body `code` 非 0；
临时 SQLite / 假 DAO，绝不碰用户真实的 `bili_note.db`。

## 覆盖

**单条删除语义**
- `test_delete_removes_row_and_all_artifact_files` —— 5 类后缀全删；不在白名单里的
  `t1_extra.bin` **不动**（宁可留残骸，也不误删别的东西）
- `test_delete_does_not_touch_other_tasks_files` —— 前缀相同的兄弟任务不被误伤（`t1` vs `t10`）
- `test_finished_task_is_deletable[SUCCESS|FAILED]` —— 终态都可删，FAILED 也是「已完成」
- `test_status_file_marks_task_in_flight` —— `code == 300106`，状态文件保留
- `test_queued_task_without_status_file_is_still_refused` —— **本 spec 的核心用例**：
  登记在册但无状态文件 → 拒绝；注销后 → 可删（守卫不能变成死锁）
- `test_corrupt_status_file_does_not_block_deletion` —— 坏文件不能把任务锁死
- `test_invalid_task_id_is_rejected[5 例]` —— `""` / 空白 / `../etc/passwd` / `a/b` / 129 字符

**批量删除**
- `test_batch_delete_is_isolated_per_item` —— 一条卡住不拖垮整批；`removed_rows` 与 `files` 也钉住
- `test_batch_delete_dedups_and_keeps_order`
- `test_batch_delete_reports_invalid_ids_in_failed`
- `test_batch_delete_rejects_empty_and_oversized`

**删除分组**
- `test_group_delete_default_keeps_notes` —— 默认模式一条笔记都不删
- `test_group_delete_with_tasks_removes_notes` —— 终态删掉、进行中跳过并退回未分组
- `test_group_delete_skips_registered_running_task_without_status_file` —— 排队中的也跳过

**运行登记表本身**
- `test_guarded_runner_unmarks_after_success`
- `test_guarded_runner_unmarks_even_on_failure` —— 抛异常也必须注销，否则永远删不掉
- `test_dispatch_registers_before_submit` —— **入队那一刻**就必须已登记
- `test_dispatch_unmarks_when_submit_fails` —— 提交失败不能留下永久登记
- `test_empty_task_id_is_never_registered`

## 踩过的坑

- **`deleted` 是字符串列表不是字典列表。** 第一版测试写 `item["task_id"] for item in data["deleted"]`
  → `TypeError: string indices must be integers`。后端在 `note.py:1849` 已经展平了。
- **`test_group_delete_skips_registered_running_task_without_status_file` 第一版期望错了**：
  只登记了 `t1`，却期望 `busy` 也被跳过 —— 而 `busy` 既无状态文件也未登记，它当然会被删掉。
- **进程级登记表必须逐用例清空**（autouse fixture），否则一个用例的「进行中」会把另一个用例锁死。
