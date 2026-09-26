# 03 · 后端：注册 openai-asr 引擎 + 透传 + 就绪门禁

- **依赖**：02
- **关联**：spec §3-8
- **状态**：✅ 已完成

## 改动点

1. `backend/app/transcriber/transcriber_provider.py`：
   - `TranscriberType` 增加 `OPENAI_ASR = "openai-asr"`；
   - `_transcribers` / `_transcriber_configs` 增加该 key；
   - `get_openai_asr_transcriber(base_url, api_key, model, timeout, max_upload_mb)`
     —— 参数全为标量，保证 `_init_transcriber` 的配置缓存能正确失效；
   - `get_transcriber(...)` 增加 `transcriber_options: Optional[dict]` 分发到该实现；
2. `backend/app/services/note.py`：
   - `_init_transcriber()` 读取 `TranscriberConfigManager`，
     若是 `openai-asr` 则取 `get_active_openai_asr()` 并把端点字段作为 `transcriber_options` 传入；
3. `TranscriberConfigManager.is_model_ready()`：
   - `openai-asr` 为在线引擎，但**未配置/未选中**端点时 `ready=False`，
     `reason='尚未配置 OpenAI 兼容 ASR，请到「设置 → 音频转写配置」添加并选择'`。
4. `backend/app/routers/config.py` 的 `AVAILABLE_TRANSCRIBER_TYPES`
   增加 `{"value": "openai-asr", "label": "OpenAI 兼容 ASR（在线）"}`。

## 验收

- 选择 `openai-asr` 时 `get_transcriber` 返回配置好的实例；
- 改了端点字段后实例按新配置重建（缓存失效）；
- 未配置端点时 `/generate_note` 返回 `transcriber_model_not_ready` 引导。
