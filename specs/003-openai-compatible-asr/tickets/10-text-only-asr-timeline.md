# 10 · 只返回文字的 ASR：时间轴插值

- **依赖**：02、08
- **关联**：spec §3
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

小米 MiMo 的 ASR 是 `chat/completions + input_audio` 风格，**只返回整段文字，没有时间轴**。
切割后每段各产生一个 `[0, 段时长]` 的粗粒度 segment，后果：

- 高价值采样的「字幕分段」几乎没有候选（一个 2 小时视频只有 2~3 个点）；
- **综合采样让 LLM 按字幕选帧时，它拿到的每行都是巨大的时间段，给不出有意义的时间点**。

对比：`transcriptions + verbose_json` 风格的 ASR 会返回逐句 `start/end`，本来就可用。

## 方案

新增 `app/utils/transcript_helper.py`：

- `split_text_into_pieces(text)`：按中英文标点切句，过长再按 60 字硬切；
- `densify_segments(segments, min_segment_seconds=20, max_segments=800)`：
  只对「跨度 > 20s 且内部没有细分」的 segment 插值——
  在其 `[start, end]` 内按**字数比例**分配每句的时间；
  插值后超过 800 段则按时间均匀抽稀；
  正规 verbose_json 的短分段**原样返回**（零影响）。

在 `services/note.py` 里，抽帧前统一把 `transcript.segments` 过一遍 `densify_segments`，
结果同时用于：
- 采样的 `subtitle_starts`；
- 综合采样的 LLM 选帧（`_plan_frames_with_llm` 改为直接接收 segments）。

> 这是**估算**而非真实对齐，但比「整段只有一个时间点」可用得多；
> 日志里会打印 `字幕时间轴插值：N 段 → M 段` 便于确认。

## 测试

`tests/003-openai-compatible-asr/test_transcript_helper.py`：
按标点切句、超长句硬切、单段 600s 插值后时间轴单调且落在原范围内、
正常短分段不被改动、空输入/无文字、段数上限。

## 验收

- MiMo 这类只回文字的 ASR 也能拿到近似逐句时间轴；
- `verbose_json` 的 ASR 行为完全不变；
- 综合采样的 LLM 选帧能基于有效时间点工作。
