# 01 · 全局冷却窗口

状态：已完成

## 做什么

在 `backend/app/utils/llm_rate_limit.py` 里加一个**进程级**的 429 冷却窗口，并把它接到 `provider_slot()` 上。

## 为什么

升级前撞上 429 只有两条路：`universal_gpt` 秒级指数退避 3 次，或 `openai_asr` 标 `non_retryable` 放弃。两者都假设「429 = 这条不行」。配额耗尽时这个假设是错的 —— 429 是「还没轮到」。

## 实现

新增 `class _RateLimitCooldown`（`_lock` / `_blocked_until` / `_first_hit_at`）：

```text
hit(cooldown_seconds, max_wait_seconds) -> bool
remaining() -> float
waited() -> float
clear() -> None
wait(chunk_seconds=1.0) -> float
```

三个要点，每个都对应一个会静默出错的地方：

1. **上限从第一次 429 起算**（`_first_hit_at`）。从最后一次起算的话，持续 429 会把窗口无限后推，「最大等待一小时」永远到不了。
2. **窗口取 max 而不是覆盖**：`_blocked_until = max(_blocked_until, now + cooldown)`。后来的 429 只延后，不提前。
3. **分片睡**（`step = max(0.05, chunk_seconds)`，循环直到 `remaining() <= 0`）。一次 `sleep(300)` 会睡过头（窗口被后来的 429 推后了），分片也让 `clear()` 能立刻生效。

公开 API：`note_rate_limit_hit`、`rate_limit_remaining`、`rate_limit_waited_seconds`、`wait_for_rate_limit`、`clear_rate_limit`、`reset_rate_limit`。

接入 `provider_slot()`：在**取信号量之前**等冷却。

```python
limiter = get_limiter(provider_key, concurrency=concurrency, max_rpm=max_rpm)
# 429 冷却窗口是**全局共享**的：任何一条任务撞上 429，所有供应商请求一起停到
# 窗口结束。放在取信号量**之前**，免得一边等冷却一边白占着并发槽位。
wait_for_rate_limit()
with limiter.slot():
    yield
```

`provider_slot` 只被 `backend/app/gpt/universal_gpt.py` 的 `_do_create` 用 —— 那是所有 LLM 请求的唯一出口。

`reset_limiters()` 末尾追加 `_RATE_LIMIT_COOLDOWN.clear()`：这是测试隔离入口，漏清冷却会让后续用例凭空睡 5 分钟。

## 配置

| 环境变量 | 默认值 |
| --- | --- |
| `RATE_LIMIT_COOLDOWN_SECONDS` | `300` |
| `RATE_LIMIT_MAX_WAIT_SECONDS` | `3600`（`0` = 不设上限） |
| `RATE_LIMIT_RESUME_INTERVAL_SECONDS` | `300` |

## 坑

- `max_wait_seconds=0` 是「不设上限、永不交还队列」，不是「立刻交还」—— 判断条件是 `if max_wait_seconds > 0 and ...`。
- 冷却常量与单例必须在 **`llm_rate_limit` 模块本身**上改。在别处 `import` 进来的同名符号是按值拷贝，改它无效（`note_rate_limit_hit()` 调用时才读模块全局）。
