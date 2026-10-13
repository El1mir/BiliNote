# 03 · 任务级退避与停放区

状态：已完成

## 做什么

把 `backend/app/routers/note.py` 的任务级重试改成「429 走等待、不消耗重试预算」，并加一个停放区让等满上限的任务把 worker 线程让出来。

## `_execute_note_with_retry` 重写

从 `for attempt in range(NOTE_MAX_RETRIES + 1)` 改成 `while True` + 双计数器（`attempt` / `rate_limit_waits`）：

| 情况 | 动作 |
| --- | --- |
| 成功 | `clear_rate_limit()` → `return note` |
| `last_error_rate_limited` 且 `note_rate_limit_hit()` 为 True | `return RATE_LIMIT_PARKED` |
| `last_error_rate_limited` 且预算未满 | `wait_for_rate_limit()` → 写 `PENDING` + `"供应商限流，等待配额恢复"` → `continue`（**不消耗 `NOTE_MAX_RETRIES`**） |
| `last_error_non_retryable` | `return None` |
| `attempt >= NOTE_MAX_RETRIES` | `return None` |
| 普通失败 | 照旧 `NOTE_RETRY_BACKOFF`（5/15/45 秒）后 `attempt += 1` |

**判断顺序不能换**：429 必须排在 `non_retryable` 前面。转写层历史上把 429 也标成了 `non_retryable`，先判后者的话 429 会被直接放弃。

## 哨兵为什么不是 `None`

```python
RATE_LIMIT_PARKED = "__rate_limit_parked__"
```

调用点是：

```python
    if not note or not note.markdown:
        ...
        breaker = _get_circuit_breaker()
        if breaker.record_failure():
            ...
```

返回 `None` 会走进这个分支 —— 计熔断、标 `FAILED`，正是这次要避免的事。所以用一个**真值**字符串哨兵。

代价：调用点必须在 `if not note or not note.markdown` **之前**拦截它，否则字符串会走进 `note.markdown` 抛 `AttributeError`：

```python
    if note == RATE_LIMIT_PARKED:
        # 429 等满上限（spec 012）：交还队列，不判失败、不计熔断。
        _park_rate_limited_task(task_id, task_kwargs)
        return
```

`run_note_task` 内部要就地组一个 20 键的 `task_kwargs`（与 `_build_task_kwargs` 的返回值一一对应），因为停放区之后要靠它重新派发。

> pyright 会把返回类型推成 `NoteResult | None | Literal['__rate_limit_parked__']`；这个 `if note == RATE_LIMIT_PARKED: ... return` 守卫同时完成了类型收窄。测试里没有该守卫，所以要写 `assert note is not None` + `assert getattr(note, "markdown", None)`。

## 停放区

进程级状态：`_PARKED_TASKS: dict` + `_PARKED_LOCK` + `_RATE_LIMIT_RESUME_STARTED`。

- `_park_rate_limited_task(task_id, task_kwargs)`：写 `PENDING` + `"供应商配额受限，等待自动恢复"` → 登记 → log「已为 429 连续等待 Ns」→ `_ensure_rate_limit_resume_loop()`。
- `parked_task_ids() -> list`：观测入口。
- `_resume_parked_tasks() -> int`：`rate_limit_remaining() > 0` 就 `return 0`；否则取出并清空停放区 → **`clear_rate_limit()`** → 逐个 `_dispatch_note_task(kwargs)`。
- `_rate_limit_resume_loop()`：`time.sleep(max(1.0, RATE_LIMIT_RESUME_INTERVAL_SECONDS))` 后调 `_resume_parked_tasks()`，异常只 log。
- `_ensure_rate_limit_resume_loop()`：幂等起线程（`daemon=True`，`name="rate-limit-resume"`）。

## 两个「为什么」

**为什么要有停放区**：worker 只有 5 个。5 条任务各抱着一条睡一小时，后面一百多条全堵死 —— 用户库里正好有 121 条失败任务，这不是假想。

**为什么恢复派发前必须 `clear_rate_limit()`**：不清的话第一次的 `_first_hit_at` 还在，任务刚派发出去就又被判「已等满一小时」，在停放区和队列之间原地打转。重新探测 = 新的等待预算。
