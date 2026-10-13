# 02 · 插图逻辑反转：判定通过才编入笔记

- **状态**：已实现
- **依赖**：01（需要 OCR 客户端；但本 ticket 的判定部分可独立先行）
- **上游 spec**：`specs/008-ocr-assist-and-legacy-cleanup/spec.md` §5

## 目标

把插图从「主模型自选时间点并直接插图」改为「笔记模型在候选帧里判定 → 只有判定通过的帧才生成、送 OCR、编入笔记」。

**判定权在笔记模型，OCR 只做下游增强。** 这是本 ticket 最容易做反的地方，见 `GLOSSARY.md` 的「OCR 辅助模式」条目。

## 现状锚点

- `backend/app/gpt/prompt.py:65-69`：`SCREENSHOT` 段落要求主模型自行发出 `*Screenshot-[mm:ss]`，并附「Only use it when truly helpful」。
- `backend/app/gpt/prompt_builder.py:104-109`：`get_screenshot_format()` 告诉模型收到的是网格图、每格左上角有时间戳。
- `backend/app/utils/screenshot_marker.py:5-13`：`extract_screenshot_timestamps(markdown)`，正则 `r"(\*?Screenshot-(?:\[(\d{2}):(\d{2})\]|(\d{2}):(\d{2})))"`。
- `backend/app/services/note.py:946-1019`：`_insert_screenshots` 无条件把每个标记替换成 ffmpeg 抽帧图。
- `backend/app/services/note.py:905-944`：`_post_process_markdown` 只在 `"screenshot" in formats and video_path` 时调用它。

## 设计要点

### 1. 候选帧清单是唯一合法时间点来源

判定必须**受候选清单约束**。模型返回的时间戳若不在清单内，该条**丢弃并记日志**，绝不能凭模型给的秒数去抽任意帧。

实现上建议把候选时间点集合作成集合，按**秒级取整**做匹配（抽帧本身就是秒级精度），并记录被丢弃的条数。

### 2. 判定契约（结构化输出）

笔记模型输出结构化判定，每条含 `time` / `worth` / `reason` / 可选 `caption`。落地要求：

- 解析失败要**按失败处理**（不静默当作「全都不值得」或「全都值得」）。
- 复用仓库已有的 JSON 解析容错思路（参考 `universal_gpt.py` 的 `parse_frame_plan`，它已经处理过「模型输出被代码块包裹」「字段缺失」等情况）。
- 判定结果落盘/记日志，便于事后复核模型是否乱判。

### 3. 提示词改造（关键：开启时才改）

- **开启 OCR 辅助时**：`SCREENSHOT` 段落必须改为「在给定候选时间点中挑选值得编入笔记的帧」，并**禁止**主模型自行发明时间戳。同时应给出明确标准，至少涵盖：含有需要精确保留的结构化内容（公式、化学式、几何图、表格、代码）、信息密度显著高于周围帧、去除后会让笔记丢信息。
- **关闭时**：见下方「实现修正」——「关闭」拆成了两层，判定层关闭时现有 `SCREENSHOT` 文案与 `get_screenshot_format()` 一字不改，走原路径。

> **实现修正（2026-02）**：本 ticket 原文把「OCR 辅助开关」当成一个开关，实现期发现它与「只有 LLM 评为要编入笔记的画面才编入」冲突，已拆成两个（见 spec §5.5 / §5.7）：
>
> - `ocr_judgement_enabled`（判定层）：关 = 上述原路径；**开 = 永不走原路径**，即使 OCR 层关着也走判定路径，只是不调 OCR、每张判定通过的图按原图插入。
> - `ocr_assist`（OCR 层）：只控制「要不要把图上文字搬进笔记」，不影响插图集合。
>
> 因此「关闭 OCR 辅助 = 输出与改动前一致」只在**判定层也关闭**时成立；只关 OCR 层时插图集合与开启时完全相同，差别仅在图上的文字是否被回填成引用块。

建议做法：把「是否 OCR 辅助」作为一个参数传进 prompt 组装函数，返回不同的截图段落，而**不是**在运行时字符串替换既有文案。

### 4. 流程接线

在 `note.py` 的生成流程中：

```
抽帧/采样 → 候选帧（时间点 + 帧图）
   → 判定（笔记模型）
   → 对 worth=true 的帧：抽单帧原图 → OCR（ticket 01 客户端）→ 生成截图 → 插入笔记
   → 对 worth=false 的帧：什么都不做
```

注意：

- 插图来源始终是**按时间点抽的单帧原图**（最高分辨率），不是网格图。网格图可以继续作为判定的上下文输入。
- OCR 内容如何并入笔记需在实现时明确（建议以图注/引用块形式附在图片旁，且**不得**改动模型已写好的正文语义）。

### 5. OCR 不可用即失败

`enabled=true` 但 OCR 未配置或调用失败时：

- 任务**直接失败**，状态为 `FAILED`，错误信息明确指向「设置 → OCR 辅助」。
- **不**降级为「跳过 OCR 直接插图」，**不**产出半成品笔记。

这与现有 `_init_transcriber()` 对 `openai-asr` 未配置时的处理风格一致（`backend/app/services/note.py:386-405` 抛「尚未配置 OpenAI 兼容 ASR，请先在「设置 → 音频转写配置」添加并选择」），建议沿用同样的错误提示风格。

### 6. 数量关系必须可观测

日志中要能看到：候选帧数、判定通过数、OCR 调用数、实际生成截图数。恒等式：

```
候选帧  ⊇  判定通过  ＝  OCR 调用数  ＝  截图数
```

这条恒等式是回归时最快发现「逻辑又做反了」的手段，建议直接加断言/告警。

## 验收

- 判定层关闭：同一视频同一设置，输出与改动前一致（重点回归项）。
- 只关 OCR 层（判定层开着）：插图集合与开启 OCR 时**完全一致**，差别仅在图上的文字是否被回填成引用块（见「实现修正」）。
- 开启 OCR 辅助：只有 `worth: true` 的帧产生截图文件；未选中的帧**没有任何图片落盘**。
- 模型给出不在候选清单内的时间戳时，该条被丢弃且有日志，不产生任意帧截图。
- OCR 未配置即为开启时，任务以明确错误失败，错误信息指向 OCR 设置页，且不产出降级笔记。
- 日志中四个计数满足上述恒等式，且六层（抽帧 / 网格 / 挑选 / 判定 / OCR / 总结）都带 `task_id`。
- 同一 `video_url` 重试时复用上一轮的抽帧与判定结果，不重复调用两次 LLM。
- 新增后端测试覆盖：候选集约束（越界时间戳被丢弃）、判定解析容错、判定层关闭时的旧路径不变、落盘与复用。

## 实现记录（2026-02）

本 ticket 已落地，下列条目为实际实现与原文的差异，均已写回 spec：

1. **判定层 / OCR 层拆分**（原文缺，见「实现修正」）：`NoteGenerator.ocr_judgement_enabled` 与 `ocr_assist` 两个字段；`_post_process_markdown` 按前者分流，`_insert_approved_screenshots(ocr_enabled=...)` 按后者决定是否调 OCR。
2. **落盘与复用**：`_ocr_cache_file` / `_load_ocr_cache` / `_save_ocr_cache`，键为 `sha1(video_url)[:16]`，带 `ocr_enabled` 标记决定可复用性（spec §5.8）。
3. **重试前清理旧截图**：`_cleanup_previous_screenshots`，按时间点删 `shot_<秒>.jpg`，不扫目录。
4. **OCR 分流判据扩到所有非 image 类**（m02915）：不只看 `formula`/`table`，任何非空 `content` 都回填成引用块。理由是 `label == "image"` 的 content 恒为 `null`，而文字型截图（整页幻灯片、代码截图）会被标成 `text`，只查 formula/table 会漏判这一大类。
5. **引用块一律带标题**（m03045）：单段用 `> **公式**` / `> **表格**`，多段用 `> **内容 N**`，让读者能分辨这段文字是 OCR 搬来的而非模型正文。
6. **按任务开关**：`VideoRequest.ocr_assist: Optional[bool] = None` 三态（`None` 跟随设置 / `True` 本次启用 / `False` 本次关闭），前端在 `NoteForm` 上以「OCR 辅助」三态 `Select` 暴露。
7. **六层日志**（m02661 `q7_logging=A`）：抽帧（smart/hybrid 与 interval 两个入口同口径）/ 网格 / 挑选 / 判定 / OCR（单张 + 聚合）/ 总结，全部带 `task_id`。
8. **OCR 客户端连接复用**：`ocr_client.get_shared_session()` 进程内共享一个 `requests.Session`，避免每张图新建连接池。

测试：`backend/tests/008-ocr-assist-and-legacy-cleanup/` 单独跑 **103 passed**；后端全量 **392 passed, 5 warnings, 13 subtests passed**。
