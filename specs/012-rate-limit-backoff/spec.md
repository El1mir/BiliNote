# 012 · 429 退避与停放

状态：`implemented`（2026-10-06）

## 1. 背景

用户在真实库里跑一次批量重试时撞上了这件事（详见 §2 现场记录）：121 条失败任务被重新入队，结果**又全部失败**，其中 **109 条根本没被尝试过** —— 它们在熔断器打开之后直接被标成 `FAILED`，错误信息是「连续失败已暂停自动执行」。

真正的根因不是代码，是供应商配额耗尽：

```text
openai.RateLimitError: Error code: 429 -
{'error': {'code': '429', 'message': 'quota exhausted', 'type': 'limitation'}}
```

而升级前的处理方式只有两条路：`universal_gpt` 里秒级指数退避重试 3 次，或者 `openai_asr` 里把 429 标成 `non_retryable` 直接放弃。两条路都建立在同一个假设上 —— **429 意味着「这条不行」**。

配额耗尽时这个假设是错的：429 意味着「**还没轮到**」。它需要的是等，不是放弃。

用户原话（m04754）：

> 再加一个功能，遇到429就停止一段时间，一段时间重试一次，最大等待一个小时，每5分钟重试一次

## 2. 现场记录（2026-10-06 实测）

- 第一次 `POST /api/retry_failed_tasks {"scope":"all","group_id":null}` → `candidates=195`、**`requeued=121`**；第二次同调用 → `requeued=0`、`skipped=195`（121 条「任务仍在执行」+ 74 条「任务状态为 SUCCESS，无需重试」）—— 端点语义正确（spec 011）。
- 重跑后终态：`SUCCESS 74 · FAILED 120 · DOWNLOADING 1 · PENDING 1`。
- FAILED 原因分布：
  - **109** 条 `连续失败已暂停自动执行，请检查配置后重新提交`（**没被尝试过**）
  - 7 条 `Error code: 429 - {'error': {'code': '429', 'message': 'quota exhausted'}}`
  - 2 条 `请求过于频繁（HTTP 429）：检查配额或稍后重试`
- 转写（ASR）部分是好的：日志可见转写缓存与音频缓存被复用（`检测到转写缓存 (note_results\<tid>_transcript.json)，直接读取`）。**卡住的只有 GPT 总结这一步。**

## 3. 目标

1. 撞上 429 **不判失败**，等一段时间再试。
2. 每 5 分钟重试一次，单条任务最长连续等 1 小时。
3. 等待期间**不占用 worker 线程**，也不把熔断器打开。

## 4. 已定决策

用户通过 `ask_user_question` 拍板（m04797）：

| 问题 | 决定 | 理由 |
| --- | --- | --- |
| 覆盖范围 | **LLM + ASR** | 两类 429 都触发「停 5 分钟再试」；B 站下载器的 429 本次不覆盖 |
| 冷却粒度 | **全局共享冷却** | 任何一条任务撞上 429，该供应商整体停到 T+5min。121 条各自睡 5 分钟会造成惊群，且各占一个 worker |
| 等满 1 小时后 | **保持排队等配额恢复**（不标 FAILED） | 与推荐项相反，用户明确选择。代价是任务可能挂很久、占着队列，但不会丢 |
| 是否计入熔断 | **不计入** | 退避等待期间的 429 不算失败；否则 5 条任务就能把熔断打开，后面的任务连等的机会都没有 |

## 5. 设计

### 5.1 全局冷却窗口

`backend/app/utils/llm_rate_limit.py` 新增进程级 `_RateLimitCooldown`：

- `hit(cooldown_seconds, max_wait_seconds) -> bool`：记一次 429，窗口 `_blocked_until = max(_blocked_until, now + cooldown)`；返回「连续等待是否已达上限」。
- **上限从第一次 429 起算**（`_first_hit_at`），不是从最后一次。从最后一次起算的话，持续 429 会把窗口无限后推，「最大等待一小时」永远到不了。
- `wait(chunk_seconds)` **分片睡**（默认 1 秒一片）：窗口会被后来的 429 推后，一次 `sleep(300)` 会睡过头；分片也让 `clear()` 能立刻生效。

接入点：`provider_slot()` 在**取并发信号量之前**调 `wait_for_rate_limit()`。

```python
limiter = get_limiter(provider_key, concurrency=concurrency, max_rpm=max_rpm)
# 429 冷却窗口是**全局共享**的：任何一条任务撞上 429，所有供应商请求一起停到
# 窗口结束。放在取信号量**之前**，免得一边等冷却一边白占着并发槽位。
wait_for_rate_limit()
with limiter.slot():
    yield
```

放在信号量**后面**的写法（`with limiter.slot(): wait_for_rate_limit()`）会让每个在途任务一边等冷却一边白占一个信号量，并发额度被锁死。

`provider_slot` 是 `backend/app/gpt/universal_gpt.py` 的 `_do_create` 用的 —— 那是本文件所有 LLM 请求的唯一出口。

### 5.2 429 判定

`is_rate_limit_error(exc) -> bool`，三条线索按可靠性从高到低：

1. `getattr(exc, "rate_limited", False) is True` —— 转写层自己打的显式标记；
2. `getattr(exc, "status_code", None) == 429` —— openai SDK 的 `RateLimitError` 带；
3. 错误文案匹配 `_RATE_LIMIT_TEXT_MARKERS`。

第 3 条不能省：本项目多处把底层异常翻成 `RuntimeError`，属性全丢。标记里包含 `"error code: 429"`、`"http 429"`、`"rate limit"`、`"ratelimit"`、`"too many requests"`、`"quota"`、`"请求过于频繁"`、`"配额"`。

> ⚠️ `"quota"` 只认词根不认整句：OpenAI 的经典 429 文案是「You exceeded your current quota」，各家措辞不一样，认整句必漏。`insufficient_quota` 严格说是计费问题、等一小时也不一定好，但用户决策是「保持排队不判失败」，所以归入等待路径是一致的。

### 5.3 两层分流：`rate_limited` 与 `non_retryable`

| 层 | 文件 | 429 归类 |
| --- | --- | --- |
| 服务层 | `backend/app/services/note.py` | `self.last_error_rate_limited = is_rate_limit_error(exc)`，**优先于** `last_error_non_retryable` |
| 转写层 | `backend/app/transcriber/openai_asr.py` | `status == 429` → `error.rate_limited = True`；`status in (400, 401, 403, 404)` → `error.non_retryable = True` |

转写层的元组原本是 `(400, 401, 403, 404, 429)` —— 429 已被摘掉。历史原因：那时「不可重试」是唯一能表达「别重跑整条流水线」的手段，所以 429 也被塞了进去。

### 5.4 任务级退避与停放区

`backend/app/routers/note.py` 的 `_execute_note_with_retry` 改为 `while True` + `attempt` / `rate_limit_waits` 双计数器：

- 成功 → `clear_rate_limit()` 后返回；
- `last_error_rate_limited` → `note_rate_limit_hit()` 为 True 则返回哨兵 `RATE_LIMIT_PARKED`；否则 `wait_for_rate_limit()`、写 `PENDING` + `"供应商限流，等待配额恢复"`、`continue`。**不消耗 `NOTE_MAX_RETRIES` 预算**；
- `last_error_non_retryable` → `return None`；
- `attempt >= NOTE_MAX_RETRIES` → `return None`；
- 普通失败照旧走 `NOTE_RETRY_BACKOFF`（5/15/45 秒）。

哨兵用字符串 `"__rate_limit_parked__"` 而不是 `None`：`None` 会被调用方计熔断并标 `FAILED`，正是这次要避免的事。调用点必须在 `if not note or not note.markdown` **之前**拦截它，否则字符串哨兵会走进 `note.markdown` 抛 `AttributeError`。

停放区（进程级）：

- `_PARKED_TASKS: dict` + `_PARKED_LOCK`；
- `_park_rate_limited_task(task_id, task_kwargs)`：写 `PENDING` + `"供应商配额受限，等待自动恢复"`、登记、启动恢复循环；
- `parked_task_ids() -> list`：观测入口；
- `_resume_parked_tasks() -> int`：冷却未结束（`rate_limit_remaining() > 0`）则返回 0；否则取出并清空停放区、**`clear_rate_limit()`**、逐个 `_dispatch_note_task(kwargs)`；
- `_rate_limit_resume_loop()`：每 `RATE_LIMIT_RESUME_INTERVAL_SECONDS` 探测一次，异常只 log；
- `_ensure_rate_limit_resume_loop()`：幂等起线程（`daemon=True`，`name="rate-limit-resume"`）。

**为什么必须清冷却**：不清的话第一次的 `_first_hit_at` 还在，任务刚派发出去就又被判「已等满一小时」，在停放区和队列之间原地打转。

### 5.5 配置

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `RATE_LIMIT_COOLDOWN_SECONDS` | `300` | 撞上 429 后的冷却时长 |
| `RATE_LIMIT_MAX_WAIT_SECONDS` | `3600` | 单条任务连续等待上限（`0` = 不设上限） |
| `RATE_LIMIT_RESUME_INTERVAL_SECONDS` | `300` | 恢复循环轮询间隔 |

> ⚠️ `RATE_LIMIT_MAX_WAIT_SECONDS=0` 的语义是「不设上限、永不交还队列」，不是「立刻交还」。

## 6. 不做什么

- **不改 B 站下载器的 429**：那是另一条链路（`bilibili_downloader`），本次范围是 LLM + ASR。
- **不把 429 的等待时间计入熔断**：见 §4。
- **不在等满上限后判失败**：用户明确选择保持排队（§4）。

## 7. 接口与可观测

新增（均在 `backend/app/utils/llm_rate_limit.py`）：

```text
note_rate_limit_hit(cooldown_seconds=None, max_wait_seconds=None) -> bool
rate_limit_remaining() -> float
rate_limit_waited_seconds() -> float
wait_for_rate_limit(chunk_seconds=1.0) -> float
clear_rate_limit() -> None
reset_rate_limit() -> None
is_rate_limit_error(exc) -> bool
```

`reset_limiters()` 现在会一并 `_RATE_LIMIT_COOLDOWN.clear()` —— 测试隔离入口漏清冷却，会让后续用例凭空睡 5 分钟。

路由模块新增：`RATE_LIMIT_PARKED`、`_park_rate_limited_task`、`parked_task_ids`、`_resume_parked_tasks`、`_ensure_rate_limit_resume_loop`。

## 8. 测试

`backend/tests/012-rate-limit-backoff/test_rate_limit_backoff.py`（32 用例），钉住五件事：

1. 429 不是失败 —— 不消耗重试预算、不计熔断；
2. 冷却窗口全局共享，且在取并发槽位**之前**等；
3. 等满上限返回 `RATE_LIMIT_PARKED` 哨兵，不标 FAILED；
4. 恢复循环重新派发前要清冷却；
5. 等待预算从第一次 429 起算。

同时 `backend/tests/005-modern-dark-ui-and-task-progress/test_openai_asr_rate_limit.py` 随行为变更更新：429 断言 `rate_limited is True` **且** `non_retryable is False`；新增 401 仍为 `non_retryable` 的用例。

## 9. 改动文件

| 文件 | 改动 |
| --- | --- |
| `backend/app/utils/llm_rate_limit.py` | `_RateLimitCooldown` + 公开 API + `is_rate_limit_error`；`provider_slot` 加等待；`reset_limiters` 清冷却 |
| `backend/app/services/note.py` | `last_error_rate_limited` 标志（优先于 `non_retryable`） |
| `backend/app/transcriber/openai_asr.py` | `_safe_transcribe` 把 429 从 `non_retryable` 改判 `rate_limited` |
| `backend/app/routers/note.py` | `_execute_note_with_retry` 双计数器重写 + `RATE_LIMIT_PARKED` + 停放区 + 恢复循环 + 调用点拦截 |
| `backend/tests/012-rate-limit-backoff/` | 新增 32 用例 |
| `backend/tests/005-.../test_openai_asr_rate_limit.py` | 契约随行为变更更新 |
