# 05 测试与验证

- 依赖：01–04
- 关联 spec：§7

## 改动点

- `backend/tests/018-single-batch-and-merged-note/`：
  `test_note_merge.py`（降级/目录/失败清单/转写合并）、`test_generate_notes_merge.py`（不建组、单任务、在途拒绝）、
  `test_merge_execution.py`（部分失败/全失败/进度）、`test_recovery_merge_payload.py`。
- `BillNote_frontend/tests/018-single-batch-and-merged-note/`：`range.test.ts`（沿用）、
  `mergePayload.test.ts`（合并/非合并请求体构造）。

## 验收

- `cd backend && .venv\\Scripts\\python.exe -m pytest tests/018-* -q` 全绿；全量 pytest 不回归。
- `cd BillNote_frontend && pnpm vitest run`、`pnpm tsc --noEmit`、`pnpm build` 通过。
