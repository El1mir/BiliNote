# 11 · chat 风格 ASR：按「说话」自动切片，时间轴取自真实静音边界

- **依赖**：02、08、10
- **关联**：spec §3-0，⚠️ 修订 10
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

`chat` 风格（小米 MiMo）的 ASR **只返回整段文字、没有时间轴**。
ticket 10 先用「按标点 + 字数比例插值」兜底，但那是**估算**。

用户提出：**按说话自动切片** —— 用静音检测找出停顿，把音频切成一段段「一次说话」，
每片单独送 ASR。这样每片的 `start/end` 就是**真实音频边界**，不是估的。

## 方案

### 切片流程（仅 `api_style="chat"`）

1. `ffmpeg silencedetect=noise=-30dB:d=0.5` 拿到所有静音区间；
2. 反推「语音区间」（静音之间的部分），丢掉 <50ms 的碎片；
3. **段数收敛**：语音区间太多时，反复合并「空隙最小」的一对，直到 ≤ `max_speech_chunks`。
   合并只连相邻区间，边界仍落在真实静音处；
4. 某个语音区间太长、切出来会超过上传上限（chat 为 base64 10MB ≈ 7.5MB 原始）时，
   再按时间等分（留 10% 余量）；
5. `ffmpeg -ss <start> -t <dur> -c copy` 逐片切出（优先不重编码，个别格式退回 64k mp3）；
6. 每片单独请求 ASR，**把该片的 start/end 直接作为返回文本的时间轴**；
7. 全部失败/检测不到静音 → 退回原来的「按大小均分切片」，行为不变。

`transcriptions` 风格（verbose_json）本来就返回逐句时间轴，**不走这条路**。

## 可配置（端点级）

静音切片的三项参数做成端点配置，在「设置 → 音频转写配置 → OpenAI 兼容 ASR」里可调
（选 `chat/completions + input_audio` 时显示）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `max_speech_chunks` | 120 | 最多切多少段；语音区间更多时按「最小空隙优先」合并 |
| `silence_noise_db` | -30 | `silencedetect` 噪声门限（dB），环境吵就调高（如 -25） |
| `min_silence_seconds` | 0.5 | 多长的停顿算「说完了」，调大 = 切得更少更粗 |

## 改动点

1. `utils/audio_helper.py` 新增：
   - `detect_speech_regions()`：静音检测 → 语音区间；
   - `merge_regions_to_limit()`：段数收敛（合并最小空隙）；
   - `cut_audio_regions()`：按区间切片，返回 `[(start, end, path)]`；
2. `transcriber/openai_asr.py`：
   - `transcript()` 在 `api_style == "chat"` 时先走 `_transcribe_by_speech()`；
   - 新增 `_split_regions_by_limit()` 处理超长语音段；
   - 单段文本用切片边界重写 `TranscriptSegment`。

## 与 ticket 10 的关系

- 切片后每段可能仍有 20s+ 的跨度 → `densify_segments` 会继续按标点插值，得到更细的近似时间轴；
- 两者叠加：**粗粒度真实边界 + 细粒度估算**，比纯估算可用得多。

## 测试

`tests/003-openai-compatible-asr/test_speech_slicing.py`（真实 ffmpeg）：

- 5s 音频（静音/音/静音/音/静音）能准确检出两段语音；
- `merge_regions_to_limit` 合并空隙最小的一对；
- chat 风格转写后**两段文本的时间轴等于真实静音边界**（1–2s / 3–4s），且发生两次请求；
- 检测不到语音时退回原路径，仍能拿到文本。

## 验收

- MiMo 这类只回文字的 ASR 也能拿到**真实语音边界**时间轴；
- 请求数有上限（默认 120 段），且可在配置页调整；
- 静音检测失败时行为与之前完全一致。
