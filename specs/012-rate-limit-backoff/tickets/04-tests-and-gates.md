# 04 · 测试与门禁

状态：已完成

## 测试文件

`backend/tests/012-rate-limit-backoff/test_rate_limit_backoff.py` —— 29 个用例（含参数化展开共 32 个 test id），约定与 009/010/011 一致：不引入 `conftest.py`；`env` fixture 自建 `FastAPI()` + `include_router(note_module.router, prefix="/api")`；业务错误仍是 HTTP 200 + 非零 body `code`。

分组：

| 组 | 用例 |
| --- | --- |
| 429 判定 | `test_rate_limit_text_is_recognised`（5 条文案参数化）、`test_non_rate_limit_text_is_not_recognised`（4 条）、`test_rate_limit_status_code_and_attribute_are_recognised` |
| 冷却窗口 | `test_hit_extends_window_and_budget_counts_from_first_hit`、`test_max_wait_zero_means_never_give_up`、`test_clear_resets_window_and_budget`、`test_wait_returns_immediately_without_cooldown`、`test_wait_sleeps_in_chunks_until_window_closes`、`test_reset_limiters_clears_cooldown`、`test_provider_slot_waits_for_cooldown_before_acquiring` |
| 任务级退避 | `test_rate_limited_does_not_consume_retry_budget`、`test_rate_limited_waiting_does_not_touch_circuit_breaker`、`test_budget_exhausted_returns_parked_sentinel`、`test_success_clears_cooldown`、`test_non_retryable_still_stops_immediately`、`test_plain_failure_still_uses_retry_budget` |
| 停放区 | `test_park_writes_pending_not_failed`、`test_resume_waits_while_cooldown_remains`、`test_resume_dispatches_and_clears_cooldown`、`test_resume_with_empty_parking_is_noop` |
| 契约 | `test_rate_limit_defaults_match_the_requirement`、`test_router_exposes_the_parking_api` |

## fixture 的两个必须项

1. **`_clean_cooldown`（`autouse=True`）前后都要 `rl.reset_rate_limit()`**。`_RATE_LIMIT_COOLDOWN` 是模块级单例，上一个用例留下的窗口会让下一个用例的 `provider_slot` 真睡 300 秒。
2. **`_fast_retry` 把 `rl.time.sleep` 与 `note_module.time.sleep` 都换成 no-op**。否则普通失败用例会真睡 5+15+45 秒。

## 三个测试自身的缺陷（写完才暴露）

- **`_StubGenerator` 表达不了「普通失败」**：`run()` 第一轮就返回 `_Note("# 笔记")` → `_execute_note_with_retry` 直接成功，`test_plain_failure_still_uses_retry_budget` 的 `assert note is None` 失败（`assert <_Note object> is None`）。加 `plain_failure=False` 参数。
- **`_RATE_LIMIT_TEXT_MARKERS` 漏文案**（这是产品代码的真缺陷，不是测试的）：见工单 02。
- **字符串哨兵的类型收窄**：`assert note is not None and note.markdown` 会报 `Cannot access attribute "markdown" for class "Literal['__rate_limit_parked__']"`。改成 `assert note is not None` + `assert getattr(note, "markdown", None)`。

## 既有测试的契约变更

`backend/tests/005-modern-dark-ui-and-task-progress/test_openai_asr_rate_limit.py`：429 从 `non_retryable` 改判 `rate_limited`，旧用例钉的是旧契约 → 见工单 02。

## 实测结果

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` | **649 passed, 2 warnings, 13 subtests passed in 62.86s**（exit 0；基线 619，spec 012 净增 29 例 + 005 净增 1 例） |
| spec 012 + 005 契约 | `pytest tests/012-rate-limit-backoff tests/005-.../test_openai_asr_rate_limit.py -q` | **32 passed, 1 warning in 5.50s** |
| 前端测试 | `cd BillNote_frontend; pnpm test` | **5 files / 24 tests passed**（651ms） |
| 前端构建 | `cd BillNote_frontend; pnpm build` | **✓ built in 48.92s**，`BUILD_EXIT=0`（仅既有 chunk >500 kB 警告） |
| 前端类型 | `pnpm exec tsc -p tsconfig.app.json --noEmit` | **110 errors**（HEAD 基线 192；spec 012 只改后端，未引入新错误） |
| pyright | `npx --yes pyright@latest backend/app/routers/note.py` | **14 errors, 0 warnings** —— 全部是既有问题，与 429 无关 |

## pyright 的 14 条（既有，未修）

`:80:18`、`:604:12`、`:1021–1025`（`run_note_task` 签名把 `model_name: str = None` 等写成非 Optional）、`:1154:28`、`:1160:21`、`:1160:46`、`:1207:31`、`:1230:13`、`:1593:12`、`:1953:12`（try 内 import + except 引用 → possibly unbound）。

其中 `:1021–1025` 的根因是 `backend/app/routers/note.py:1014-1036` 的 `run_note_task` 签名。修它要把 `model_name`、`provider_id`、`_format`、`style`、`extras` 全改成 `Optional[...]`，会牵动调用方 —— **本次不动**，避免在 429 改造里混入无关的类型重构。

> `lens_diagnostics mode=full refreshRunners=cheap` 对刚改过的文件会报成片假错（如 `"reset_rate_limit" is not a known attribute of module "app.utils.llm_rate_limit"`）—— 那是 LSP 未重新索引，符号实际存在于 `backend/app/utils/llm_rate_limit.py`。判定以 `grep` 源码 + 实际跑测试为准。
