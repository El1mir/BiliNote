# 02 · 后端：OpenAIASRTranscriber

- **依赖**：01
- **关联**：spec §3-3/4/5/6、§4.3
- **状态**：✅ 已完成

## 改动点

新建 `backend/app/transcriber/openai_asr.py`：

1. 把 `GroqTranscriber` 里的 `compress_audio()` 抽成公共函数
   （放在 `backend/app/utils/audio_helper.py`，Groq 也改为复用，保持行为不变）；
2. `OpenAIASRTranscriber(Transcriber)`：
   - `__init__(base_url, api_key, model, timeout=600, max_upload_mb=18, name="")`；
   - `transcript(file_path)`：
     a. `os.path.getsize` 超 `max_upload_mb` → 压缩；
     b. `build_openai_client(api_key, base_url, timeout=timeout, key_label=...)`；
     c. 请求 `response_format="verbose_json"`；
     d. 若抛错且错误信息含 `response_format` → 依次回退 `json` → `text`；
     e. 解析：`verbose_json.segments` → `TranscriptSegment[]`；否则单段（0 ~ 文件时长）；
     f. 返回 `TranscriptResult`；
   - 失败直接把异常抛给上层（不吞、不回退本地 whisper）。

## 追加（2026-09-26）：错误信息人性化

用户填了非 ASR 的 OpenAI 兼容地址（如只提供 chat 的 `.../v1`）时，openresty 会返回
一整页 HTML 404，原样糊到界面上没有可读性。新增 `_friendly_error()`：

- 去掉 HTML 标签并截断（不再回显整页 404）；
- 按 `status_code` 翻译：404 → 「该 Base URL 下没有 /audio/transcriptions」、
  401/403 → 鉴权失败、400 → 模型名/能力问题、429 → 配额、5xx → 服务端错误、超时 → 提示调大超时；
- 返回 HTML 但无状态码 → 提示「该地址可能不是 OpenAI 兼容接口」。

## 验收

- 支持 OpenAI 官方与自建 whisper 服务（verbose_json）；
- 只支持 `json`/`text` 的服务也能用（退化成单段）；
- 超时按配置生效；大文件先压缩再传；
  — ⚠️ 2026-09-26 修订：改为**切割多段**，不再压缩（见 ticket 09）
- 地址填错时给出可读原因（不再回显 HTML）。
