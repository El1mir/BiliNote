# 02 · 429 判定与两层分流

状态：已完成

## 做什么

让「429」这件事在服务层和转写层都能被认出来，并且**归类为「等」而不是「放弃」**。

## `is_rate_limit_error(exc) -> bool`

三条线索，按可靠性从高到低：

1. `getattr(exc, "rate_limited", False) is True` —— 转写层自己打的显式标记；
2. `getattr(exc, "status_code", None) == 429` —— openai SDK 的 `RateLimitError` 带；
3. 文案匹配 `_RATE_LIMIT_TEXT_MARKERS`。

**第 3 条不能省**：本项目多处把底层异常翻成 `RuntimeError`，属性全丢。

标记表：`"error code: 429"`、`"http 429"`、`"rate limit"`、`"ratelimit"`、`"too many requests"`、`"quota"`、`"请求过于频繁"`、`"配额"`。

> ⚠️ `"quota"` 只认词根。第一版写的是 `"quota exhausted"` / `"insufficient quota"` 两个整句，结果 OpenAI 的经典文案「You exceeded your current quota」直接漏掉（`test_rate_limit_text_is_recognised[You exceeded your current quota]` 失败）。**各家措辞不一样，认整句必漏。**

## 服务层 `backend/app/services/note.py`

- `__init__` 加 `self.last_error_rate_limited = False`；
- `generate()` 的 try 开头重置它；
- `generate()` 的 except 里在 `self.last_error_non_retryable = ...` **之前**加：

```python
            # 429 优先于 non_retryable：转写层历史上把 429 也标成了不可重试
            # （那时「不可重试」是唯一能表达「别重跑整条流水线」的手段），
            # spec 012 起 429 改走等待路径，所以这里必须先判它。
            self.last_error_rate_limited = is_rate_limit_error(exc)
```

`__init__` 里那条注释也从「429/鉴权等错误不应触发任务级重试」改成「鉴权/参数等错误不应触发任务级重试」—— 429 已经不在这个集合里了。

## 转写层 `backend/app/transcriber/openai_asr.py`

`_safe_transcribe` 的 except：

```python
            error = RuntimeError(_friendly_error(exc))
            status = getattr(exc, "status_code", None)
            # 429 与其它 4xx 分开（spec 012）：配额/频率受限是「还没轮到」，应当等
            # 冷却窗口后重试；而鉴权失败、模型不存在重跑整条流程只会重复下载和切片。
            if status == 429:
                error.rate_limited = True  # type: ignore[attr-defined]
            elif status in (400, 401, 403, 404):
                error.non_retryable = True  # type: ignore[attr-defined]
            raise error from exc
```

原元组是 `(400, 401, 403, 404, 429)` —— **429 已摘掉**。

## 契约变更（既有测试要跟着改）

`backend/tests/005-modern-dark-ui-and-task-progress/test_openai_asr_rate_limit.py::test_rate_limit_error_is_marked_non_retryable` 钉的是旧契约（429 → `non_retryable`），全量回归时报 `AssertionError: assert False is True`。这是**预期的行为变更，不是 bug**。

改法：用例改名 `test_rate_limit_error_is_marked_rate_limited_not_non_retryable`，断言 `rate_limited is True` **且** `non_retryable is False`；另加 `test_auth_error_is_still_non_retryable`（401 → `non_retryable is True`、`rate_limited is False`）。抽出 `_transcriber_raising(monkeypatch, error)` 辅助函数避免重复。
