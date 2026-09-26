# 04 · 后端：路由 CRUD + 测试连接

- **依赖**：01、02
- **关联**：spec §4.2
- **状态**：✅ 已完成

## 改动点

`backend/app/routers/config.py`：

1. `GET /transcriber_config` 改用 `get_public_config()`，返回里带
   `openai_asr_endpoints`（打码）与 `openai_asr_id`；
2. `POST /transcriber_config` 请求体增加 `openai_asr_id`；
3. 新增：
   - `POST /openai_asr`（`OpenAIASREndpointRequest`）→ 新增，返回 `{id}`；
   - `POST /openai_asr/{id}` → 更新；
   - `DELETE /openai_asr/{id}` → 删除；
   - `POST /openai_asr/{id}/test` → 生成 1 秒静音 wav，调用该端点做一次真实转写，
     返回 `{ok, message}`（失败不 500，返回可读原因）。
4. 错误统一用 `R.error(msg=...)`，不要把异常栈抛给前端。

## 验收

- CRUD 正常；`GET` 不返回完整 key；
- 测试连接能区分「鉴权失败 / 地址不通 / 模型不存在」并给出可读信息。
