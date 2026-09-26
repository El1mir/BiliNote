# 08 · 支持 chat/completions + input_audio 风格（小米 MiMo）

- **依赖**：01-06
- **关联**：spec §3-9、§4.1
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

用户接入小米 MiMo 时按 `/v1/audio/transcriptions` 配置，得到 openresty 的 **404 HTML**。
查文档与实测确认：

- MiMo 的 Speech Recognition（`mimo-v2.5-asr`）**不是** Whisper 风格的
  `/audio/transcriptions`，而是走 **`POST /v1/chat/completions`**
  + `messages[].content[].input_audio`（base64 音频），属于「OpenAI chat + 音频输入」风格；
- 实测 `https://token-plan-cn.xiaomimimo.com/v1/chat/completions` → **401**（接口存在），
  而 `.../v1/audio/transcriptions` → **404**；
- 文档约束：base64 后不能超过 **10MB**，仅支持 wav / mp3。

所以「OpenAI 兼容 ASR」需要能表达**两种请求风格**。

## 已定语义

端点新增 `api_style`，**二选一**：

| 值 | 请求 | 适用 |
|---|---|---|
| `transcriptions`（默认） | `POST {base_url}/audio/transcriptions`，`response_format` 可降级 | OpenAI Whisper / 硅基流动 / 自建 whisper-server |
| `chat` | `POST {base_url}/chat/completions`，`content[].input_audio.data` 传 base64 data URL | 小米 MiMo `mimo-v2.5-asr`、gpt-4o-audio 类 |

`chat` 风格补充规则：

- 音频统一转 base64 data URL；
- ⚠️ 2026-09-26 修订（ticket 09）：超过 `min(chunk_size_mb, 7.5MB)` 时**切成多段**分别转写再合并，
  不再压缩；每段各自 base64 都在 10MB 以内；
- 返回取 `choices[0].message.content`（无时间戳 → 造一个覆盖全片的单段）。

## 改动点

### 后端
1. `TranscriberConfigManager`：端点新增 `api_style`（默认 `transcriptions`），校验取值；
2. `OpenAIASRTranscriber`：新增 `api_style` 参数与 `chat` 分支
   （`_prepare_for_chat` / `_create_chat_completion` / `_chat_text`）；
3. `get_openai_asr_transcriber` / `get_transcriber` 透传 `api_style`；
4. `OpenAISREndpointRequest` 与 `/openai_asr` CRUD、`/openai_asr/{id}/test` 透传。

### 前端
5. `services/transcriber.ts`：`OpenAIASRStyle` 类型；
6. 转写配置页端点表单新增「接口类型」下拉，并在说明里给出两种风格各自的服务示例。

## 测试

- `test_openai_asr_transcriber.py`：chat 风格请求体（`input_audio` + mime）、content 解析、
  超大音频报错、未知 style 回退；
- `test_config_manager.py` / `test_routes.py`：`api_style` 默认值、更新、非法值校验。

## 验收

- 选择 `chat` 风格后，可用 MiMo 的 `mimo-v2.5-asr` 完成转写；
- 选择 `transcriptions` 风格时行为与之前完全一致；
- 音频超过 base64 上限时自动切成多段，而不是让服务端返回 400。
