# 05 · 前端：transcriber 服务类型与接口

- **依赖**：04
- **关联**：spec §4.2
- **状态**：✅ 已完成

## 改动点

`BillNote_frontend/src/services/transcriber.ts`：

1. `TranscriberConfig` 增加 `openai_asr_id?: string`、
   `openai_asr_endpoints?: OpenAIASREndpoint[]`；
2. 新增类型 `OpenAIASREndpoint`：`id/name/base_url/api_key/model/timeout/max_upload_mb`；
3. `updateTranscriberConfig` 入参增加 `openai_asr_id?`；
4. 新增方法：
   - `addOpenaiAsr(data)` / `updateOpenaiAsr(id, data)` / `deleteOpenaiAsr(id)`
   - `testOpenaiAsr(id)` → `{ ok: boolean; message: string }`

## 验收

- 类型与后端返回一致；方法路径与 spec §4.2 一致。
