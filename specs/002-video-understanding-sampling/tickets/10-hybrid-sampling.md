# 10 · 综合采样（高价值 + 均匀 + LLM 按字幕选帧）

- **依赖**：01-09
- **关联**：spec §1A、§3、§4.2
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

用户提出：在「间隔采样 / 高价值帧采样」之外再加一个**综合采样**，
把三路来源**全都用上**：

1. **高价值帧**：画面变化（场景切换）+ 字幕分段；
2. **均匀采样**：整段视频均匀铺点，保证覆盖度（ticket 09 的兜底）；
3. **LLM 按字幕选帧**：把带时间戳的字幕交给 LLM，让它判断「哪里值得截图」
   （出现 PPT / 图表 / 公式 / 代码 / 演示，或话题切换），回传结构化的时间点。

## 已定语义

- 采样方式新增 `sampling_mode="hybrid"`（下拉文案就叫「**综合采样**」，不带括号说明——太长会挤掉右边的参数框）。
- **配额**（三路都参与，约 40 / 30 / 30）：

  | 来源 | 名额 | 说明 |
  |---|---|---|
  | LLM 选帧 | `max_frames * 0.4` | 最懂内容，先占位；超出则按时间均匀取 |
  | 高价值（场景+字幕） | `max_frames * 0.3` | 画面/语音变化点 |
  | 均匀采样 | 剩余全部 | 保证整段覆盖 |

  某一路候选不够，多出来的名额自动让给均匀采样。
- **LLM 用当前笔记模型**（表单里选的 `model_name` / `provider_id`），复用 `UniversalGPT` 客户端，
  不新增供应商配置；温度 0.2，最多一次请求/视频。
- **字幕过长**时按时间均匀抽稀到最多 600 段，控制 prompt 体积（保留整段覆盖）。
- **失败自动降级**：没有字幕 / 模型不支持 / 调用异常 → 只用「高价值 + 均匀」，
  **不影响任务本身**。
- `hybrid` 只用 `max_frames`（全片上限），不使用「限制方式」二选一（那是 smart 的）。
- `max_frames` **不设上限**（下限 5）：几小时的课程需要更大预算；
  注意拼图张数 = `ceil(max_frames / (列 × 行))`，帧数调大时同步调大「拼图尺寸」，
  否则单次多模态请求会塞进几百张图。
- `hybrid` 同样**关闭逐帧 MD5 去重**（同 ticket 09）。

### LLM 结构化输出

```json
{"frames": [{"time": 123.4, "reason": "开始讲解 XX 流程图"}]}
```

解析容错：markdown 代码块、纯数组、`timestamp`/`start` 字段名、非 JSON 时正则兜底；
最后统一做**越界过滤**（必须落在 `0 ~ duration`）。

## 改动点

### 后端
1. `utils/frame_sampler.select_hybrid_timestamps(...)`：三路合并 + 配额 + 均匀补满；
2. `gpt/universal_gpt.plan_frame_timestamps(...)` + `FRAME_PLAN_PROMPT` + `parse_frame_plan(...)`；
3. `services/note._plan_frames_with_llm(...)`：调 LLM 选帧并兜底；
   `generate()` 的抽帧分支扩展到 `smart | hybrid`；
4. `utils/video_reader.VideoReader`：新增 `llm_timestamps`，`hybrid` 走 `select_hybrid_timestamps`。

### 前端
5. 采样方式下拉新增「综合采样」（文案保持简短，避免撑爆参数区）；
6. 选中 hybrid 时只显示「最大帧数」，不显示「限制方式」。

## 修复记录

- **2026-09-26**：LLM 选帧一直失败，报 `KeyError: '"frames"'`。
  原因是 `FRAME_PLAN_PROMPT` 里含 JSON 示例 `{"frames": [...]}`，
  而代码用 `prompt.format(duration=..., max_items=...)` 填充 —— `str.format`
  把 `{"frames"}` 当成占位符，直接抛 `KeyError`。
  改为 `{DURATION}` / `{MAX_ITEMS}` 占位符 + `str.replace()` 填充（JSON 花括号保持字面量）；
  失败日志补上 `exc_info=True` 便于定位。
  同时修了 `test_universal_gpt_content_format.py` / `test_universal_gpt_checkpoint.py`
  泄漏 `sys.modules` stub 的问题（会让后续测试拿到假的 `TranscriptSegment`）。

## 测试

- `test_hybrid_sampling.py`：三路都参与、无 LLM 时降级、无时长时不补均匀点、
  越界过滤、`parse_frame_plan` 多种返回形态、note.py 的兜底与配额透传、
  VideoReader 透传 `llm_timestamps` 且关闭 MD5 去重。

## 验收

- 选「综合采样」后，抽到的帧里三路来源都有；
- 帧数接近 `max_frames` 且覆盖整段视频；
- LLM 不可用/返回异常时任务照常完成（自动降级，不报错）；
- 批量模式下每个视频各自选帧。
