# 01 · ASR 分段并发转写

- **依赖**：—
- **关联**：spec §4 决策 1–3、§5
- **状态**：已完成

## 目标

把「逐段请求 ASR」从串行改成受配置约束的并发，吃掉已经付费/配置好的并发额度。

## 改动点

1. `openai_asr.py`：`OpenAIASRTranscriber.__init__` 新增 `chunk_concurrency`（默认 4，clamp 1–32），
   环境变量兜底 `OPENAI_ASR_CHUNK_CONCURRENCY`。
2. `_transcribe_by_speech()`：`cut_audio_regions()` 之后用
   `ThreadPoolExecutor(max_workers=min(concurrency, cpu_count))` + `executor.map` 并发转写，
   **保序**收集结果；进度用 `threading.Lock` 保护的计数器累加后回报。
3. `_transcribe_in_chunks()`：同样并发，偏移量按段序计算，保持时间轴正确。
4. `_RateLimiter` 保持唯一入口（`_create_transcription` / `_create_chat_completion` 内部 `wait()`），
   并发不会突破 `max_rpm`；`chunk_concurrency=1` 即回到串行行为。
5. 并发体内的异常原样抛出（`executor.map` 迭代时即抛出），走既有 `non_retryable` 判定。

## 验收

- 80 段转写耗时随并发度近似线性下降（受限流封顶），结果段数与顺序与串行完全一致。
- `chunk_concurrency=1` 时行为与改动前一致。
- 限流测试：并发下每分钟请求数不超过 `max_rpm`（见 ticket 06）。
