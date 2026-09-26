# 01 · 后端：TranscriberConfigManager 扩展

- **依赖**：无
- **关联**：spec §3-1/2/7、§4.1
- **状态**：✅ 已完成

## 改动点

`backend/app/services/transcriber_config_manager.py`：

1. `get_config()` 增加 `openai_asr_id`、`openai_asr_endpoints`（原始值，含真实 api_key）；
2. `get_public_config()`：在 `get_config()` 基础上对每个端点的 `api_key` 打码
   （复用 `ProviderService.mask_key` 或等价实现），供路由返回前端；
3. `update_config(transcriber_type, whisper_model_size=None, openai_asr_id=None)`；
4. 端点 CRUD：
   - `add_openai_asr(name, base_url, api_key, model, timeout=600, max_upload_mb=18) -> id`
   - `update_openai_asr(id, **fields)`（`api_key` 含 `*` 视为未改动，跳过）
   - `delete_openai_asr(id)`（删除后若为 active 则清空 `openai_asr_id`）
   - `list_openai_asr()` / `get_openai_asr(id)` / `get_active_openai_asr()`
5. 字段校验：`base_url` / `api_key` / `model` / `name` 非空；`timeout>0`；`max_upload_mb>0`。

## 验收

- 新增/更新/删除持久化到 `config/transcriber.json`；
- `get_public_config()` 不泄漏完整 api_key；
- 删除 active 端点后 `openai_asr_id` 自动清空。
