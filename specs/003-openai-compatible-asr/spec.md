# 003 · OpenAI 兼容 ASR 引擎（替代本地 ASR）

- **状态**：implemented（2026-09-26 全部工单完成）
- **日期**：2026-09-26
- **范围**：转写引擎扩展（backend）+ 音频转写配置页（frontend）
- **上游**：spec 001 / 002 无关；本 spec 新增一个转写引擎类型。
- **动机**：本地 faster-whisper 在 CPU 上慢（实测 tiny 也要 ~180s/视频）。
  用户希望接入 **OpenAI 音频转写格式**（`POST /v1/audio/transcriptions`）的在线服务
  （OpenAI / 硅基流动 / 自建 whisper 服务等）来替代本地 ASR。

---

## 1. 目标

新增一个转写引擎类型 **`openai-asr`**，特征：

1. **两种 OpenAI 风格**（端点级 `api_style` 二选一，见 §3-9）：
   - `transcriptions`：`client.audio.transcriptions.create(...)`，任意兼容
     `/audio/transcriptions` 的服务；
   - `chat`：`chat.completions` + `input_audio`，如小米 MiMo `mimo-v2.5-asr`；
2. **可配置**：`base_url` / `api_key` / `model` 由用户在「音频转写配置」页填写；
3. **可添加多条并切换**：像模型供应商一样维护一个列表，选中其中一条作为当前使用；
4. **超时可配**：默认给较长超时（默认 600s），避免长音频被拦；
5. **超阈值自动切割**：上传文件超过可配「切割阈值」（默认 18MB）时切成多段分别转写再合并（不再压缩）；
6. **失败不静默回退**：在线 ASR 失败即任务失败并把原因透出，由用户去切换引擎/模型。

> 现状参考：`GroqTranscriber` 已经是「OpenAI 格式 + 硬编码 provider=groq + 模型读环境变量」
> 的特例。本 spec 把它泛化成可配置的通用实现，Groq 引擎保留不动。

## 2. 非目标

- 不改造/删除现有引擎（fast-whisper / mlx-whisper / bcut / kuaishou / groq）。
- 不做本地 ASR 与在线 ASR 的自动 fallback（明确不静默回退）。
- 不做流式转写 / 实时字幕。
- 不把 ASR 配置写进 `providers` 表（避免污染 LLM 供应商列表）。

## 3. 已定决策

| # | 决策 | 结论 |
|---|---|---|
| 1 | 配置存放 | 存 `config/transcriber.json`，单独一组字段，不进 `providers` 表 |
| 0 | 时间轴 | `verbose_json` 的 ASR 直接用其逐句时间轴；只回文字的（MiMo chat）**按说话（静音边界）自动切片**，用真实语音边界当时间轴，再按标点插值细化（ticket 10/11） |
| 2 | 数量 | 支持**多条** OpenAI 兼容 ASR 配置，可切换当前使用的一条 |
| 3 | 请求格式 | `response_format="verbose_json"`；服务端不支持时**回退** `json`/`text` |
| 4 | 超时 | 每条配置独立 `timeout`（秒），默认 **600** |
| 5 | 大文件 | 超过 `chunk_size_mb`（默认 **18**）**切成多段分别转写再合并**（2026-09-26 改为切割，ticket 09） |
| 6 | 失败处理 | 直接失败并透出错误原因，**不**自动回退本地 whisper |
| 7 | API Key 存储 | 同 providers，明文存 config；**GET 接口返回时打码**，未改动则不覆盖 |
| 8 | 就绪门禁 | `openai-asr` 在线，但**未配置/未选中**任何一条时判为未就绪并给出引导 |
| 9 | 接口风格 | 端点级 `api_style` 二选一：`transcriptions`（/audio/transcriptions）/ `chat`（chat/completions + input_audio），后者用于小米 MiMo `mimo-v2.5-asr`（2026-09-26 追加，ticket 08） |

## 4. 接口/配置草案

### 4.1 `config/transcriber.json`

```json
{
  "transcriber_type": "openai-asr",
  "whisper_model_size": "tiny",
  "openai_asr_id": "<active-id>",
  "openai_asr_endpoints": [
    {
      "id": "b1c2...",
      "name": "硅基流动",
      "base_url": "https://api.siliconflow.cn/v1",
      "api_key": "sk-...",
      "model": "FunAudioLLM/SenseVoiceSmall",
      "timeout": 600,
      "chunk_size_mb": 18,
      "api_style": "transcriptions"
    },
    {
      "id": "d4e5...",
      "name": "小米 MiMo",
      "base_url": "https://api.xiaomimimo.com/v1",
      "api_key": "sk-...",
      "model": "mimo-v2.5-asr",
      "timeout": 600,
      "chunk_size_mb": 7,
      "api_style": "chat"
    }
  ]
}
```

### 4.2 路由

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/transcriber_config` | 返回配置（`openai_asr_endpoints[].api_key` 打码） |
| POST | `/api/transcriber_config` | 保存 `transcriber_type` / `whisper_model_size` / `openai_asr_id` |
| POST | `/api/openai_asr` | 新增一条（返回新 id） |
| POST | `/api/openai_asr/{id}` | 更新一条 |
| DELETE | `/api/openai_asr/{id}` | 删除一条 |
| POST | `/api/openai_asr/{id}/test` | 用一段静音音频测试连通性/鉴权 |

### 4.3 转写器实现

`OpenAIASRTranscriber(base_url, api_key, model, timeout, chunk_size_mb, name, api_style)`：

1. 文件**未超阈值** → 直接单次请求；
2. 文件**超阈值** → `split_audio()` 切成 N 段（`N = ceil(size / 阈值)`），
   每段各自请求，再按累计时长**平移时间戳合并**（不再压缩，见 ticket 09）；
3. 两种请求风格：
   - `transcriptions.create(..., response_format="verbose_json")`，报错提示不支持时降级 `json` → `text`；
   - `chat.completions.create(...)` + `input_audio`（base64 data URL）；
4. 有 `segments` 就用；否则用 `full_text` 造一个覆盖本段时长的单段；
5. 返回 `TranscriptResult(language, full_text, segments, raw)`。

## 5. 实现清单

| # | 工单 | 状态 |
|---|---|---|
| 01 | 后端：`TranscriberConfigManager` 扩展（多端点 CRUD + 激活 + 打码） | ✅ 已完成 |
| 02 | 后端：`OpenAIASRTranscriber`（压缩 + format 回退 + 超时） | ✅ 已完成 |
| 03 | 后端:注册 `openai-asr` 引擎 + 透传配置 + 就绪门禁 | ✅ 已完成 |
| 04 | 后端：路由 CRUD + 测试连接 | ✅ 已完成 |
| 05 | 前端：`services/transcriber.ts` 类型与接口 | ✅ 已完成 |
| 06 | 前端：音频转写配置页 OpenAI 兼容 ASR 管理 UI | ✅ 已完成 |
| 07 | 测试：后端单测 + 前端交互 | ✅ 已完成 |
| 08 | chat/completions + input_audio 风格（小米 MiMo）（ticket 08） | ✅ 已完成 |
| 09 | 过大的音频改为切割多段（替代压缩）（ticket 09） | ✅ 已完成 |
| 10 | 只返回文字的 ASR：时间轴插值（ticket 10） | ✅ 已完成 |
| 11 | chat 风格：按说话自动切片，时间轴取真实静音边界（ticket 11） | ✅ 已完成 |
| 11a | 静音切片参数入端点配置（最多切片数 / 静音门限 / 最短静音）（ticket 11） | ✅ 已完成 |

## 6. 决策记录

- 配置存放 / 数量 / 失败行为 / 大文件处理：均已在 §3 确认并实现。
- 未做自动 fallback：在线 ASR 失败即任务失败，用户自行切换引擎（符合 §3-6）。
- 2026-09-26 追加：接入小米 MiMo 时发现其 ASR 走 chat/completions + input_audio，
  故引入端点级 `api_style` 二选一（§3-9，ticket 08）。
- 2026-09-26 追加：过大的音频从「压缩」改为「切割多段」，`max_upload_mb` → `chunk_size_mb`
  （§3-5，ticket 09；旧配置自动兼容）。
- 2026-09-26 追加：chat 风格没有时间轴 → 用静音检测按「说话」自动切片，每片单独转写并用真实语音边界当时间轴（§3-0，ticket 11）。
