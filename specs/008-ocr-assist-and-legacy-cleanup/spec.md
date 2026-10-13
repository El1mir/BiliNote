# 008 · OCR 辅助模式与旧版功能清理

- **状态**：implemented
- **日期**：2026-10-03（⚠️ 2026-10-06 追加 §12.8：提示词全面改写与两处召回缺陷修复）
- **范围**：OCR 辅助模式（可配置 glm-ocr 类模型）、插图逻辑反转、删除「重新生成」与「笔记版本管理」、本地缓存与历史任务重置
- **上游**：002 / 005 / 006 / 007

## 1. 背景

当前「原片截图」是**由主笔记模型自行决定**插图位置的：`prompt.py` 的 SCREENSHOT 段落要求模型在「视觉演示、代码走查、UI 交互」处自行发出 `*Screenshot-[mm:ss]` 标记，`_insert_screenshots` 再把这些标记替换成 ffmpeg 抽帧图片。

这带来三个问题：

1. **模型在盲选**。主模型看到的是网格图，网格里每格是一个缩小的时间点，它据此决定「哪一段值得配图」，但没有能力判断真正的价值所在 —— 例如化学结构式、立体几何图、乐谱、电路图。这类内容的价值不在「这一段在讲什么」，而在「这一帧上有没有一张信息密度极高的图」。网格图的分辨率也不足以支撑这种判断。
2. **没有 OCR 通道**。图片里承载的文字与公式（化学式、几何标注、代码截图）只能靠多模态模型「看一眼」，无法被结构化提取，因此笔记里丢失了图上的精确内容。
3. **图片进入笔记的门槛太低**。模型倾向于多发标记，`Only use it when truly helpful` 约束不住，导致笔记里塞入大量信息量低的过程帧。

同时，仓库里有两项历史遗留功能需要清理：

- **「重新生成」**：前端 `NoteForm.tsx` 的 `editing` 状态锁死表单，提交时走 `retryTask` 复用同一个 `task_id`，后端 `note.py` 有对应的 `if data.task_id:` 复用分支。它把「生成一份新笔记」和「重跑一个失败任务」两件事搅在一起。
- **「笔记版本管理」**：前端把 markdown 包成 `Markdown[]` 版本数组（新版本前插），配一个版本下拉框。后端结构上无法表示多版本（`NoteResult.markdown: str`），版本只存在于浏览器 IndexedDB。它源自单次提交 `97f1536`，没有对应 spec，且引入了 newest/oldest 的读取不一致 bug（`chat_tools.py` 取 `md[-1]` 实际拿到的是最旧版本）。

## 2. 目标

1. 新增**独立的 OCR 辅助模式**：可由用户配置一个 glm-ocr 类的版面/文字识别模型，任务流程中用它提取图片内的结构化内容。
2. **反转插图逻辑**：只有当**笔记模型判定某张图值得编入笔记**时，该图才进入笔记；未被评为值得的图不生成、不插入。OCR 只对**已被选中**的候选图做下游增强，不承担「判定是否值得」的职责。
3. OCR 辅助模式**默认关闭**；关闭时行为与当前完全一致，不改变任何既有笔记结果。
4. 删除「重新生成」功能，前端与后端一并移除。
5. 删除「笔记版本管理」功能，markdown 收敛为 `string`。
6. 提供一次性重置脚本，清理本地中间产物、截图、笔记产物、`video_tasks` 记录与向量集合；浏览器端通过 persist 版本号提升丢弃旧任务列表。

## 3. 非目标

- **不**把 OCR 结果当作插图位置的决定者。判定权始终在笔记模型（见 §4 决策 4 与 §5）。
- **不**新建数据库表来存 OCR 模型配置（走独立 JSON 配置文件，见 §4 决策 1）。
- **不**改造浏览器扩展（`BillNote_extension` 对这两个待删功能零引用，无需改动）。
- **不**在 OCR 不可用时静默降级（见 §4 决策 5）。
- **不**保留旧任务列表的兼容渲染；旧数据直接丢弃（见 §4 决策 6b）。

## 4. 已定决策

| # | 决策 | 结论 |
| --- | --- | --- |
| 1 | OCR 模型配置位置 | 新建「OCR 辅助」设置页；配置存 `config/ocr.json`，复用 `TranscriberConfigManager` 的管理模式；**不**新增数据库表 |
| 2 | 与「原片截图/视频理解」的关系 | 独立开关。开启时插图完全由判定驱动，**主模型不再自行发 `*Screenshot-*` 标记**；关闭时行为与现状完全一致 |
| 3 | OCR 输入图像 | 按采样时间点抽出的**单帧原图**（最高分辨率）；时间戳精确，因此不需要在图上烧录网格角标 |
| 4 | 谁终审「编入笔记」 | **笔记模型判定哪张图值得插入笔记，仅这些图送去 OCR**。OCR 是对已选中候选的下游增强，不是判定关口 |
| 5 | OCR 不可用 | **任务直接失败**并提示用户去配置 OCR，不降级 |
| 6 | 清空范围 | 彻底重置生成物：中间产物 + 截图 + `note_results` + `video_tasks` 行 + Chroma 集合 + 浏览器任务列表 |
| 6b | 清空方式 | 一次性脚本清后端 + 前端 persist 版本号提升，自动丢弃旧任务列表 |
| 7 | 删「重新生成」 | 前端后端一起删：连 `task_id` 复用分支和失败重试按钮都删（覆盖审计中「重试按钮必须保留」的建议） |
| 8 | 删「版本管理」 | markdown 收敛为 `string`；读取时取最新版本兜底 |
| 9 | 规格归属 | 新建 `specs/008-ocr-assist-and-legacy-cleanup/` |

## 5. 插图逻辑反转（核心）

### 5.1 现状

```
主模型收到网格图 → 自行发出 *Screenshot-[mm:ss] → 抽出该时间点截图 → 插入笔记
```

模型的判定与插图请求是同一个动作：它发出标记，系统就无条件插图。

### 5.2 反转后

```
采样抽帧 → 候选帧清单（时间点 + 帧图）
   ↓
笔记模型评估候选帧，给出「值得编入笔记」的判定 + 理由
   ↓
仅被选中的帧 → OCR 提取结构化内容 → 生成截图 → 连同 OCR 结果编入笔记
   ↓
未选中的帧 → 不 OCR、不生成、不插入
```

关键点：**判定先于 OCR**。OCR 的输入集合是被笔记模型筛过的子集，因此 OCR 调用量与费用只与「真正编入笔记的图」成正比，而不是与采样帧数成正比。

### 5.3 判定契约

笔记模型不再自选时间点，而是**在给定的候选帧里挑选**。它输出结构化判定（JSON），每条含：

- `time`：候选帧的时间戳（必须来自候选清单）
- `worth`：布尔，是否值得编入笔记
- `reason`：判定理由（用于日志与人工复核）
- `caption`：建议的图注（可选）

系统据此：丢弃 `worth: false`；对 `worth: true` 的帧按其时间点抽原图、送 OCR、插入笔记。

判定必须**受候选清单约束**：模型 hallucinate 一个不在清单里的时间戳时，该条必须被丢弃并记日志，不能凭模型给的秒数去抽任意帧。

### 5.4 与网格图的关系

网格图仍可作为判定的**输入上下文**（帮助模型理解视频在讲什么），但网格图本身不再是「插图来源」。插图的像素来源始终是按时间点抽出的单帧原图，以保证分辨率。

### 5.5 关闭时

> **本节在实现期被推翻过一次，下面是修正后的结论。**原文写的是「关闭 = 完全走既有路径，不做判定」，实现时发现这个定义与需求 §2.2 直接冲突，故按实现结论修订。

「关闭」不是一个开关，而是**两个**（详见 §5.7）：

| 层 | 字段 | 关闭后的行为 |
| --- | --- | --- |
| 判定层 | `ocr_judgement_enabled` | 退回既有路径：SCREENSHOT 提示词照发，主模型自行发 `*Screenshot-[mm:ss]`，`_insert_screenshots` 照旧替换。**不**做判定、不改变输出 |
| OCR 层 | `ocr_assist` | 判定照跑、插图集合完全不变，只是**不调 OCR**：每张判定通过的图按原图插入 |

关键点：**关掉 OCR 辅助 ≠ 关掉「画面值不值得编入笔记」**。

原因是需求 §2.2 的不变量「候选帧 ⊇ 判定通过 ⊇ 实际插入」必须无条件成立。若把 OCR 开关同时当成判定开关，那么在「用户想要插图但没配 OCR」的环境里就只能退回老路径，主模型自写的 `*Screenshot-` 会绕过判定直接进笔记——这正是本 spec 要消灭的行为。所以判定层必须独立于 OCR 服务存在：**判定只用笔记模型，不需要 OCR 服务。**

判定层因此也没有配置项：只要开「编入笔记的图片」就走判定（`generate()` 里 `self.ocr_judgement_enabled = True`）。没有候选帧时不是失败，只记 WARNING 并插图为零（见 §5.7）。

### 5.6 代码走查补充（2026-10-03，来自流水线全链路走查）

以下三条是走查后新增的事实，直接影响反转的实现方式。

**a) 判定应当复用已有的选帧设施。** 仓库里已经有一套「让模型挑值得截图的时间点」的机制，不必新造：

- `backend/app/gpt/universal_gpt.py:380-396` `FRAME_PLAN_PROMPT`，挑帧标准已经写明「幻灯片 / 图表 / 公式 / 代码 / 表格 / 流程图 / 软件演示」——这正是本需求要保留的那类内容。
- `backend/app/gpt/universal_gpt.py:399-425` `parse_frame_plan`，已容错处理代码块包裹、纯数组、字段名差异（`frames|timestamps|data|result`）。
- `backend/app/services/note.py:359-384` `_plan_frames_with_llm` 是现成的调用入口。

但要注意职责差异：`FRAME_PLAN_PROMPT` 现在是**选帧给多模态模型看**（hybrid 采样的一个配额来源，`HYBRID_LLM_RATIO = 0.4`），而本需求要的是**选帧编入笔记**。二者标准相近但目的不同，**不可直接复用同一个提示词而不做区分**——否则会改变 hybrid 采样的既有行为。做法应是新增一个判定用的提示词/方法，复用其解析容错与调用形态。

**b) 现有选帧机制的已知缺陷必须一并修掉。** `_plan_frames_with_llm` 在解析失败或调用异常时返回**空列表**（`backend/app/services/note.py:359-384` 内 `return []`），而调用方 `parse_frame_plan` 的返回值会被静默接受。本需求下这意味着「一次网络抖动 = 全笔记没有插图」。因此判定路径必须：

- 区分「模型明确判定没有值得的帧」与「调用/解析失败」——前者是合法结果，后者是错误；
- 失败时按 ticket 02 §5 的失败策略处理（提示 + 不产出静默降级的笔记），而不是当成「没有值得的帧」。

**c) 框选时间点必须校验，现状不校验。** 走查确认 `_insert_screenshots`（`backend/app/services/note.py:946-1019`）**不校验**标记时间点是否在采样集合内——模型给任何 `mm:ss` 都会被抽帧。这既是本需求 §5.3「候选清单约束」要修的问题，也是既有缺陷。

**d) 已有真实的图片数量数据可用作护栏依据。** `backend/note_results/*.json` 里单篇笔记的插图数实测分布为 2 ~ 173 张（`aa5a2774` = 173、`273e7b06` = 66、`62858ab8` = 63，而 `b7996e71` / `b865d541` 只有 2 张）。单篇 173 张说明「无上界发标记」是现实存在的问题。判定路径应设置**每次笔记的插图数量上限**，并在超过时记日志（上限值在 ticket 02 中确定）。

**e) 时间戳只有两位分钟。** `backend/app/utils/screenshot_marker.py:6` 的正则是 `\d{2}:\d{2}`，超过 99 分钟的视频无法表达。判定路径改为**结构化输出以秒为单位的数值**（如 `time: 123.4`，与 `FRAME_PLAN_PROMPT` 一致）即可规避该限制，这也是采用 JSON 判定契约而非标记契约的额外理由。

### 5.7 判定层与 OCR 层是两个独立概念

规格原文把「OCR 辅助模式」当成一个开关，实现期拆成两个，语义如下（对应 `NoteGenerator` 的两个实例字段）：

```python
self.ocr_judgement_enabled: bool = False   # 挑选 + 判定要不要跑
self.ocr_assist: bool = False              # OCR 层：要不要把图上的文字搬进笔记
```

两者的关系不是「包含」而是「正交」：

- 判定层**不依赖** OCR 服务（只用笔记模型），所以没配 OCR 的环境也能满足「只有 LLM 评为要编入笔记的画面才进笔记」。
- OCR 层**依赖**判定层：没有判定通过的画面就没有可 OCR 的对象。
- `ocr_assist=True` 而 `ocr_judgement_enabled=False` 是不可能的组合（`ocr_assist` 只在判定层内部被读取）。

**开关的来源分两层：**

- 「设置 → OCR 辅助」页管**配没配好**（`config/ocr.json` 的 `enabled` / `ready`）。
- 生成表单管**这次用不用**，三态覆盖 `VideoRequest.ocr_assist: Optional[bool] = None`：
  - `None`（默认，前端「跟随设置」）= 沿用全局开关；
  - `True`（「本次启用」）= 强制开，即使全局开关关着也继续走 readiness 检查后启用；
  - `False`（「本次关闭」）= 强制关，**只关 OCR 层**，判定层照跑。

**没有候选帧不算失败。** 判定层开着但抽帧产出为空时，记 WARNING，笔记正常生成、插图为零。这与「判定调用/解析失败必须让任务失败」（§5.3）是两件事：前者是合法结果，后者是错误。

**重试前清理上一轮截图。** 同一时间点的截图文件名固定为 `shot_<秒>.jpg`，重试会覆盖写同名文件；不清理就会在 `static/screenshots/` 留下不再被任何 markdown 引用的残骸（实测单篇最多 173 张）。因此插图前按本轮判定通过的时间点逐个删除对应文件，**不扫目录**（避免误删其他任务的图）。

### 5.8 判定结果的落盘与重试复用

抽帧、挑选、判定三层加起来可能是几十分钟的 CPU 与两次 LLM 调用（§5.6d 记录了 814 秒的实例）。任务因下游失败而重试时，这三层的结果必须能复用，否则重试等于从零再来。

- **缓存键是 `video_url`，不是 `task_id`。** 重试会换一个新的 `task_id`，用 `task_id` 做键等于每次都落空。实现为 `sha1(video_url)[:16]` 的短哈希文件名 `ocr_frames_<hash>.json`，落在 `NOTE_OUTPUT_DIR`。
- **落盘时机在判定成功之后。** 判定失败时写盘会把「判定通过 = 空」这种未完成状态固化下来，反而让下一次重试以为已经算完了。
- **读回必须还原成 `WorthDecision` 数据类。** 落盘用 `asdict`，下游却全靠 `getattr(decision, "time")` 取时间戳；读回 dict 会让所有截图落在 0 秒那一帧。
- **缓存里带 `ocr_enabled` 标记。** 上一轮「没跑 OCR」的缓存不能被「这一轮要跑 OCR」的调用复用，否则开关打开后仍会拿到没有 OCR 结果的笔记。
- **内存优先。** 实例上已经有本轮结果时（`approved_shots is not None`）不读盘；`None` 的语义是「还没算过」而非「算过了、结果为空」，这个区别是复用逻辑成立的前提。
- **缓存坏了当没有。** 落盘是优化，损坏的 JSON 只记 WARNING，不能让任务失败。

## 6. OCR 辅助模式配置

新增「OCR 辅助」设置页，配置项最少包含：

- `enabled`：总开关，默认 `false`
- `provider_type` / `base_url` / `api_key` / `model_name`
- 连接测试入口
- `max_pages` / 图像大小上限等受模型约束的护栏项

配置文件 `config/ocr.json`，与 `transcriber` 的配置管理方式一致（独立 JSON、独立页面、不动数据库表）。API key 在读取接口中必须脱敏返回，仅在写入时接受明文。

设置页只表达「**配没配好**」；「**这次用不用**」由生成表单上的三态开关表达（见 §5.7）。两者不可合并：把开关只放在设置页，就无法「偶尔关一次」；只放在表单，就没有地方存 API Key。

## 7. 删除「重新生成」

删除范围（前端与后端一并）：

- 前端 `NoteForm.tsx`：`editing` 状态、`disabled={!!editing}` 锁定、`'重新生成'` 标签、`新建笔记` 按钮、`handleCreateNew`、以及提交时 `if (currentTaskId) { retryTask(...) }` 的短路分支。表单不再被选中任务锁死。
- 前端失败重试按钮（`MarkdownViewer.tsx` 的 `重试`）与 store 的 `retryTask` 一并移除（用户明确要求）。
- 后端 `note.py` 的 `if data.task_id:` 复用分支移除；`task_id` 不再由客户端提供，服务端一律新建。
- 移除后，重复生成同一视频将永远创建新任务；若保留按视频去重的进行中检查，需在 ticket 中明确其语义。

## 8. 删除「笔记版本管理」

- 前端 `Markdown` 接口、`Task.markdown` 的联合类型收敛为 `string`。
- `updateTaskContent` 不再包装版本对象，直接赋值；保留其幂等保护。
- `MarkdownHeader` 的版本下拉、`MarkdownViewer` 的 `currentVerId` / `isMultiVersion` 及两个版本 effect 全部删除。
- **读取兜底**：IndexedDB 里 `task-storage` 可能已有数组形态的旧数据。读取时用容错读取（`Array.isArray(md) ? md[0].content : md`）取**最新**版本 —— 注意数组是**新版本在前**，取 `md[0]`，不是 `md[md.length-1]`。
- 后端 `chat_tools.py` 的数组分支可一并简化（其 `md[-1]` 取到的是最旧版本，是既有 bug）。
- 文档同步：`README.md` 的「支持多版本记录保留」、`specs/005` ticket 11 的「Markdown 版本能力」需一并修订。

## 9. 本地缓存与历史任务重置

一次性脚本（建议 `scripts/reset_local_state.py`），范围：

| 目标 | 说明 |
| --- | --- |
| `backend/data/output_frames/` | 抽帧中间产物（约 158MB） |
| `backend/data/grid_output/` | 拼图中间产物（约 14.4MB） |
| `backend/static/screenshots/` | 生成的截图（约 111MB / 644 文件） |
| `backend/note_results/` | 笔记产物、字幕缓存、状态文件、`.tmp` 残留 |
| `video_tasks` 表 | 历史任务记录 |
| `media_resources` / `media_cleanup_runs` | 与上述资源配套的登记与审计行 |
| Chroma 集合 | `backend/vector_db/` 下的向量集合 |
| `backend/logs/app.log` | 日志（可选，需在 ticket 明确） |

要求：脚本默认**干跑**（只报告将删除什么、共多少字节），必须显式传参才真正删除；不触碰 `backend/models/`（whisper 模型 564MB）、`.venv/`、数据库文件本身、用户配置。

同时清理已知的**孤儿表**（无 ORM、无代码引用）：`media_resource_refs`、`note_versions`、`note_groups`、`note_migration_markers`、`note_migration_diagnostics`。注意 `note_versions` 这一孤儿表是历史遗留，与本次要删除的**前端**版本管理无关。

前端 sidebar 的旧任务列表通过 persist 版本号提升自动丢弃。

## 10. 验收

- 关闭 OCR 辅助时，同一视频同一设置的输出与改动前一致。
- 开启 OCR 辅助时：仅 `worth: true` 的候选帧产生截图并出现在笔记中；未选中的帧没有图片文件落盘。
- 笔记模型给出的时间戳不在候选清单内时，该条被丢弃且有日志，不产生任意帧截图。
- OCR 未配置即为开启时，任务以明确错误失败，错误信息指向 OCR 设置页，且**不**产生降级笔记。
- 候选帧判定、OCR 调用、截图生成三者的数量关系符合「判定 ⊇ OCR = 截图」。
- 「重新生成」在全仓库无残留：`重新生成` 字面量、`editing` 锁、`task_id` 复用分支、失败重试按钮均已移除。
- 「版本管理」在全仓库无残留：无 `ver_id`、无 `isMultiVersion`、无版本下拉；旧的数组形态 IndexedDB 数据仍能渲染出最新一版笔记而非空白。
- 重置脚本干跑输出准确；执行后中间产物、截图、`note_results`、`video_tasks`、Chroma 集合均为空，且模型目录/配置/数据库文件未被误删。
- 判定层与 OCR 层可独立开关：关掉 OCR 时插图集合与开启时**完全一致**，只是图上的文字不回填（§5.7）。
- 生成表单上的三态开关能覆盖设置页：`跟随设置` / `本次启用` / `本次关闭` 三种选择都如实传给后端（`VideoRequest.ocr_assist`）。
- 重试复用生效：同一 `video_url` 的第二次尝试不再重复抽帧与两次 LLM 调用，且复用的是判定结果本身而不是「判定通过 = 空」。
- 后端测试、前端测试、生产构建通过。

## 11. 待确认问题

> **两个问题均已于 2026-10-04 关闭**，结论见 `tickets/01-api-verification.md` §9。
> 保留原文以记录它们在规格写作时的状态。

- ~~GLM-OCR 的**接线细节**（端点路径、请求体字段、鉴权头是否带 `Bearer`、单文件大小与页数上限）在规格写作时尚无一手文档可核实，ticket 01 必须先落地一份可复现的接口验证记录，并把这些可能变动的项做成**可配置**。~~
  → 已真机验证：端点 `/api/paas/v4/layout_parsing`、鉴权 `Bearer`、请求体 `{model, file}`、图片 ≤10MB 全部确认。**「做成可配置」这一要求已被反向执行**：验证后改成了常量（§12.5），只保留 `base_url` / `model_name` / 三个护栏可配。
- ~~`max_pages` 一类护栏的默认值待接口验证后确定。~~
  → 取保守值 30（国内站文档 100、国际站 30，取小者）。本功能只发单帧图片，护栏实际只对 PDF 输入生效，PDF 场景仍未实测。

## 12. 实现记录（2026-02 落地）

### 12.1 交付物

后端新增：

- `backend/app/services/ocr_config_manager.py` —— `config/ocr.json` 配置层，与 `TranscriberConfigManager` 同构（独立 JSON、不动数据库表）。
- `backend/app/services/ocr_client.py` —— 调用层。**2026-10-04 收敛为智谱 glm-ocr 专用**：只走 `POST {base_url}/api/paas/v4/layout_parsing`，端点路径 / 鉴权头形态 / 文件字段名 / 响应取值路径均为模块常量；原先的 `layout_parsing` + `openai_chat` 双协议适配器已删除（见 ticket 01 §9）。
- `backend/app/services/ocr_test_image.py` —— `make_test_image()` 现画 900×340 ASCII 测试图。
- `backend/app/services/ocr_assist.py` —— 判定契约（提示词、解析、上限、对照表渲染）。
- `backend/app/routers/ocr.py` —— `GET /api/ocr_config`、`POST /api/ocr_config`、`POST /api/ocr_config/test`，已注册进 `backend/app/__init__.py`。原先的 `GET /api/ocr_config/protocols` 已随协议抽象一并删除。

后端改动：

- `backend/app/gpt/utils.py` —— 新增 `load_llm_json()`，`parse_frame_plan` 与判定解析共用，避免两处容错分叉。
- `backend/app/gpt/universal_gpt.py` —— 新增 `judge_note_frames()`；`create_messages` / `summarize` 透传 `ocr_assist` + `approved_shots`；`_build_source_signature` 纳入这两个字段（否则切换模式会命中旧 checkpoint）。
- `backend/app/gpt/prompt_builder.py` —— 新增 `get_ocr_assist_screenshot_format()`；`get_format_function` 对 `'screenshot'` 分流。
- `backend/app/models/gpt_model.py` —— `GPTSource` 新增 `ocr_assist` / `approved_shots`。
- `backend/app/utils/video_reader.py` —— 新增 `candidate_timestamps`，只记真正落盘的帧（自动排除被 `dedupe_enabled` 删掉的）。
- `backend/app/services/note.py` —— 新增 `_resolve_ocr_assist` / `_judge_note_frames` / `_insert_approved_screenshots`；两处抽帧入口都记候选清单。
- `backend/app/routers/note.py` —— 删除 `task_id` 入参与重试分支。
- `backend/app/services/chat_tools.py` —— `_get_note_content` 的兼容读由 `md[-1]` 改为 `md[0]`。

前端：

- 新增 `BillNote_frontend/src/services/ocr.ts`、`BillNote_frontend/src/pages/SettingPage/ocr.tsx`，并在 `SettingPage/Menu.tsx` 与 `App.tsx` 注册。
- `BillNote_frontend/src/store/taskStore/index.ts`（新增 `readLatestMarkdown`、删 `Markdown` 接口与 `retryTask`、persist `version: 2`）、`src/hooks/useTaskPolling.ts`、`pages/HomePage/components/MarkdownViewer.tsx`、`MarkdownHeader.tsx`、`NoteForm.tsx`。

文档：`GLOSSARY.md`（新增术语，含两个「已废弃概念」）、本 spec、`README.md` 删除「支持多版本记录保留」。

### 12.1b 实现期对规格的修正（2026-02）

1. **§5.5 被推翻重写。** 原文「关闭 = 完全走老路径」与 §2.2 的不变量冲突，改为「判定层 / OCR 层两开关」（§5.7）。连带影响：`post_process_markdown` 的分流条件从 `if self.ocr_assist:` 改为 `if self.ocr_judgement_enabled:`，`_insert_approved_screenshots` 新增 `ocr_enabled` 参数。
2. **新增判定结果的落盘与复用**（§5.8）：`_ocr_cache_file` / `_load_ocr_cache` / `_save_ocr_cache` 三个方法，外加 `_cleanup_previous_screenshots`。
3. **新增按任务的 OCR 开关**：`VideoRequest.ocr_assist` → `run_note_task(ocr_assist=...)` → `generator.generate(ocr_assist=...)` → `_resolve_ocr_assist(override)`；前端 `NoteForm` 的三态 `Select` 与 `services/note.ts` 的 `generateNote` 类型同步。
4. **六层日志补齐**（抽帧 / 网格 / 挑选 / 判定 / OCR / 总结），全部带 `task_id`，依据 m02661 `q7_logging=A`。抽帧层两个入口（smart/hybrid 与 interval）口径一致。
5. **OCR 客户端的连接复用**：`ocr_client.get_shared_session()` 提供进程内共享 `requests.Session`，`OcrClient(config, session=None)` 默认用它。此外 `_insert_approved_screenshots` 把 `build_ocr_client()` 提到 worker 循环**之外**——原先它在 `_render` 内部，而 `_render` 每张图调一次，于是 N 张图要重复 N 次读 config 与构造适配器，与旁边「共用一个进程级 client」的注释自相矛盾。现在每次插图只建一次，`test_ocr_client_is_built_once_per_insert_not_once_per_image` 锁住这条。

### 12.2 验证

- 后端全量：`cd backend; .venv\Scripts\python.exe -m pytest -q --no-header` → **393 passed, 5 warnings, 13 subtests passed**（收尾改动后；spec 008 目录内单独跑为 104 passed）。
- 前端生产构建：`npx vite build` → 成功（`✓ built in 59.59s`）。
- ESLint 净变化为零：`NoteForm.tsx` / `services/note.ts` 相对 HEAD 无新增告警（HEAD 7 errors + 2 warnings → 现 3 errors + 2 warnings，少的 4 条是已被清掉的未使用导入）。
- pyright `backend/app/services/note.py`：HEAD 45 errors → 收尾后 28 errors（只降不升，无回归）。
- 真机 OCR 调用：本节记录时**未做**；**已于 2026-10-04 完成**，见 §12.5 与 `tickets/01-api-verification.md` §9。

### 12.3 实现期发现并修掉的两个既有缺陷

1. **`backend/tests/006-note-pipeline-performance/` 的两个测试永久污染 `sys.modules`**：它们为单独载入 `bilibili_downloader.py`，把 `app` / `app.services` 等换成没有 `__path__` 的裸模块且从不还原，导致同进程里其后任何真正 `import app.services.xxx` 的测试报 `No module named 'app.services.ocr_test_image'; 'app.services' is not a package`。按目录名排序 `tests/008-*` 正好排在 `tests/006-*` 之后，所以**只有跑全量才暴露**。已补上「记录 + 还原」。
2. **`backend/app/services/chat_tools.py` 的兼容读取错端**：`md[-1]` 拿到的是最旧一版，与注释「取最新」相反。已改为 `md[0]`，与前端 `readLatestMarkdown` 一致。

### 12.4 已知残余

- `universal_gpt.py` 的判定调用走 `_chat_completion_create`（带重试），而 `plan_frame_timestamps` 仍是裸 create；两者重试策略不一致，本次未统一。
- `_insert_screenshots`（判定层关闭时的老路径）仍然不校验时间戳是否落在候选清单内 —— 这是 §5.6c 记录的既有缺陷。「判定层关闭」仍然要求输出与改动前逐字一致，故**故意不改**；判定层开启后走的是新路径，不存在该问题。
- 真机 OCR 端到端调用**已于 2026-10-04 完成**（国内站 + 真实截图），`bbox_2d` 量纲（0–1）、`label=="image"` 恒空、`formula.content` 是 LaTeX 三项由推定转为实测，见 `tickets/01-api-verification.md` §9。**国际站（`api.z.ai`）仍未实测**。
- 判定提示词要求模型为每个批准时间点插入一次 `[[SHOT-n]]`；模型漏插时该帧被追加到笔记末尾的「补充截图」小节，而不是丢弃。

### 12.5 智谱专用收敛（2026-10-04）

真机验证完成后按用户要求「不要做通用，先专门写成智谱清言的」删掉了双协议抽象。**规格层面这是一次有意识的收窄**，理由是通用抽象存在的唯一前提（接线细节不确定）已被实测消除：

| 变化 | 内容 |
| --- | --- |
| 配置面 | 11 个字段 → **7 个**（`enabled` / `base_url` / `api_key` / `model_name` / `timeout` / `max_file_mb` / `max_pages`） |
| 代码 | `protocol` / `endpoint_path` / `auth_scheme` / `file_field` / `response_path` / `prompt` / `extra_params` 全部改为模块常量或删除 |
| API | 删除 `GET /api/ocr_config/protocols` |
| 前端 | 删除协议下拉框与 6 个底层字段输入框；卡片「高级（兼容性）」改名为「请求限制」 |
| 兼容 | 旧配置文件**读时忽略**已删键、不报错、不迁移；写回时只落 7 个键 |

**判据（为什么现在敢收窄）**：端点、鉴权头、文件字段名、响应取值路径全部已实测确认，不再有需要靠配置兜的未知量；而这些字段在设置页是用户无法回答的问题（「响应取值路径」不该问用户）。

**代价（已接受）**：原先配 `openai_chat` + 硅基流动的用户，升级后那套 key 会被拿去打智谱端点并失败。此为预期：配置不会损坏，但需改成智谱 Key。401/403 已标为不可重试，所以不会白跑三轮。

**真机暴露并修掉的三个缺陷**：认证失败被无意义重试（`OcrError.non_retryable`）、`OcrConfigManager` 相对路径依赖 CWD（静默读空配置）、`generate_screenshot` 的 ffmpeg 无 timeout（会永久阻塞任务且无日志）。

### 12.6 收敛后的验证

- 后端全量 `pytest -q` → **409 passed, 5 warnings, 13 subtests passed**（收敛前 393；+16 来自改写的测试用例）。
- spec 008 目录 → **120 passed**。
- 前端 `npx vite build` → 成功（`✓ built in 1m 3s`）；OCR chunk 由 14.83 kB 降到 **10.74 kB**（被删掉的协议抽象不再进包）。
- 真机回归：用收敛后的 `OcrClient` 打真实截图，返回 `protocol=layout_parsing, markdown=332, blocks=4`，与收敛前**逐块一致**（text/image/text/formula，bbox 相同）→ 行为零回归。
- 旧配置升级实测：老格式文件可读不报错、用户字段保留、协议残留被忽略、写回后磁盘只剩 7 个键。

### 12.7 策略反转：OCR 提前 + 判定通过的图一律插图（2026-10-04）

**这一节推翻 §5.2「OCR 读出内容时用引用块顶替插图」与 §5.3 的分流判据。**

#### 用户决策（m04445）

原策略把「OCR 读出了什么」当成「要不要插图」的判据：读出公式/表格 → 用引用块顶替，
不插图。用户指出这恰好搞反了价值判断：

> 无论 ocr 有没有返回内容，大模型评估应该插入的图片都应该被插入

理由很直接——**一张图画质清晰、文字抄得下来，反而最容易触发「以文字顶替」，于是笔记里
恰恰看不到那张最该被看到的图**。板书、公式、幻灯片整页都是这一类。引用块里的 LaTeX 也
不等于原图的版面信息（行列对齐、上下标位置、图示关系都在图里）。

#### 新策略

| 维度 | 旧 | 新 |
| --- | --- | --- |
| 判定通过的图 | 看 OCR 结果决定插图 or 回填文字 | **一律插图** |
| OCR 结果的去处 | 渲染成引用块插进正文 | 汇总成**参考块**送进总结提示词 |
| OCR 失败 | 上抛，整个任务 FAILED | 跳过该张的参考内容，**图照插**，任务继续 |
| OCR 执行时机 | 插入阶段（`_insert_approved_screenshots` 内） | 总结**之前**独立一层（`_run_ocr_stage`） |
| 送总结模型的图 | 网格图（127 张 3×3 拼图） | 判定通过的**单帧**截图 |

最后一行是「OCR 提前」的实质收益：判定层要的是吞吐（127 张网格图），总结层要的是清晰度
（一张板书截成 1/9 谁都看不清）。两者此前共用同一份 `video_img_urls`，属于把判定层的工作
材料直接塞给总结层。

#### 契约变化

- **不变量改写**：`候选帧 ⊇ 判定通过 ＝ 实际插图`。OCR 成败**不再**进入这条等式——它只
  决定「有没有额外文字参考可送给模型」。
- **占位符计数恒等式**从 `候选帧 ⊇ 判定通过 ⊇ 实际插入 ＝ OCR 调用数` 改为上式的
  `embedded != len(approved)` 检查。
- **「判定通过但没有可插入位置」不再降级成文字**：仍追加到「## 补充截图」小节。
- `build_ocr_quote` **保留**（公共 API，有独立测试），但不再被产品路径调用；
  `_OCR_QUOTE_LIMIT = 4000` 因失去唯一消费者而删除。
- `ocr_texts` 存的是 **`OcrResult`**（带 `blocks` 的 bbox 与 `raw["md_results"]`），
  不是分流用的瘦身视图 `OcrReading`。存错类型不会报错，只会让参考块静默退化成
  「图上没有可提取的文字」——这正是本轮测试抓到的问题。

#### 参考块的形状

`build_ocr_reference(shots, readings)` 按时间点分节，每节给模型三样东西：

```
### [[SHOT-1]] @ 00:12
- 判定理由：推导公式
- 说明：薛定谔方程
- 内容  第 1 段（formula）：
    i\hbar\partial_t\psi = \hat{H}\psi
- 版面元素：
    image bbox=[0, 0, 1, 1]
    formula bbox=[0.1, 0.2, 0.3, 0.4]
- md_results 原文：
    板书：薛定谔方程
```

`label == "image"` 元素跳过（它恒 `content: null`，是插图元素而非正文），与
`classify_ocr_result` 同口径。OCR 完全没结果时明说「未返回结果（该图仍会插入笔记）」，
防止模型把「没有参考」误读成「这里没东西」。

提示词里的措辞是**参考资料**，且明确要求「不要原样照搬整块内容，也不要为它单独开一节」、
「每个 `[[SHOT-n]]` 仍然只对应一张即将插入的截图」——不写清楚的话，模型会既插了图又把
同样内容抄一遍，或者把参考块当成已有的 `[[SHOT-n]]` 索引去数错图。

#### 验证

- spec 008 目录 → **136 passed**（从 129 起，改写 8 条旧策略测试 + 新增 8 条 pivot 测试）。
- 后端全量 → **425 passed, 5 warnings, 13 subtests passed**。
- pyright：`note.py` **27 errors**（HEAD 45，且新写的 `_run_ocr_stage` 区域 0 报错）、
  `universal_gpt.py` **2**（HEAD 9）、`ocr_assist.py` / `prompt_builder.py` / `gpt_model.py` **0**。
- 参考块落盘往返一致、`float(shot.time)` 取键与 `_run_ocr_stage` 同源，
  已在进程内自检确认。

#### 改写测试时的一条纪律

那 8 条失败的旧测试分两类，处理方式不同，值得记下来：

- **断言的正是被推翻的策略**（5 条）→ 必须**改写断言**而不是删掉。断言是规格的可执行
  表述；策略反转后，旧断言就是过时的规格描述，直接删掉等于把「曾经要求过什么」也删了。
- **只是测内部实现位置**（3 条）→ 行为没变、实现搬了家，**重新指向新结构**并补上对新层的
  覆盖（`_run_ocr_stage` 的 client 复用与失败跳过）。

### 12.8 提示词全面改写与两处召回缺陷（2026-10-06，来源 m07537）

#### 事故

用户贴出的生产日志里两条任务失败，异常原文：

```text
Exception: 没能从字幕里挑出任何值得截图的画面，OCR 辅助模式无法继续
（请确认视频有可用字幕，或关闭「设置 → OCR 辅助」后重试）
```

失败点是**挑选层**（`note.py::_pick_note_frames` 对空结果抛硬异常），不是判定层、
不是 OCR 层、不是下载层。两条任务各重试 2/3 次全部失败。

#### 根因

`FRAME_PLAN_PROMPT` 末条写着「确实没有值得截图的地方就返回 `{"frames": []}`」——
这既是**逃生口**，又没有**召回下限**。失败任务 `8eac7042`（p198）的字幕只有 7 段、
全是 ASR 错字（`想避免散涼快逍` / `散念散的心`…），模型于是**合法地**交白卷。
用一次性回路脚本原样复现：

- `BV147411K7xu_p198.mp3`（77.1s / 7 段）→ 模型原始输出 `'{"frames":[]}'`，**exit=1（RED）**；
- 对照 `BV147411K7xu_p12.mp3`（925.9s / 570 段）→ 45 条挑选、`picks=24`，exit=0。

即：同一提示词在长而干净的字幕上正常，在短/低质量字幕上必然失败。日志里另有
**挑选层命中候选帧 0/39、8/44、5/200、2/146** 的极低命中率，是第二处独立缺陷（见下）。

#### 修复一：挑选层提示词 + 召回下限 + 兜底

`universal_gpt.py`：

- 新增 `PLAN_COVERAGE_SECONDS = 30`（覆盖密度：每 30 秒至少一个候选点）。
- `FRAME_PLAN_PROMPT` 重写：显式说明「字幕来自自动语音识别，可能有错别字，这**不是**
  「没有值得截图的地方」的理由」；「必须挑」清单加入「讲题、例题、习题、题干、选项、
  答案、解题步骤」与「举例子、做演示、画图、给出结论」；新增「数量是硬性要求，不是建议」
  段（`至少 {MIN_ITEMS} 项；相邻两个时间点之间不要超过 {MAX_GAP} 秒`、宁多勿少）；空数组
  被收窄为「只有整段视频确实没有任何画面内容（纯音频、纯口述）时才允许」。
- 新增 `plan_min_items(duration, max_items)`：`ceil(duration / 30)`，下限 3、上限
  `max_items`，**绝不返回 0**；`build_frame_plan_prompt(duration, max_items)` 用 `replace`
  填 5 个占位符（模板含 JSON 示例花括号，不能用 `str.format`）。
- `plan_frame_timestamps` 增加两道兜底：① 时长探测失败时用字幕末尾
  `segments[-1].end` 顶替（没有时长就没有「均匀覆盖」，而均匀覆盖是模型交白卷时唯一的
  救生索）；② 解析结果为空 → `uniform_frame_plan(duration, max_items)` 均匀内插 + `warning`。
  理由写进代码注释：**漏挑一帧只是少一张图，交白卷是整条任务失败，两者代价不对称**。

#### 修复二：判定层与生成层提示词

- `ocr_assist.py::WORTH_JUDGE_PROMPT`：基调从「要严格、宁可少判」反转为**宁多勿少、
  拿不准一律判 true**；true 清单首位加入「题目 / 例题 / 习题 / 题干 / 选项 / 答案 /
  解题步骤——哪怕只是题目的一角」；false 清单收窄为「只有这几种」，并**删除**原
  「字幕已经完整表达了画面里的全部信息」这条（它正是漏图的主因）。
- `prompt.py::BASE_PROMPT`：规则 2 收窄为「只省略广告、口头禅、寒暄和闲聊，**不要**以
  「精简」为由删掉知识点、例题或推导过程」；规则 3 要求题目/例题/习题完整保留（题干、
  已知条件、选项、答案、解题步骤一个都不能少）；规则 5 补「符号、下标、上标和括号要写
  准确」；**新增规则 6「修正转写错误」**（ASR 有错别字要修正，但不要因为读不通就跳过）。

#### 修复三：候选帧吸附（非提示词缺陷）

`note.py::generate` 原来用**毫秒精确相等**求交：`round(t, 3) in candidate_set`。
但挑选层的时间戳来自字幕（`31.5` / `60.1` 这类小数），候选帧来自 interval 抽帧
（`range(0, int(duration), frame_interval)`，**整秒**）——两者本来就对不齐，精确相等
几乎必然落空。这就是上面 0/39、8/44、5/200 的机制，也让两次 LLM 调用白跑。

改为新增 `_match_candidate_frames(picked, candidates, tolerance=None)`：把每个挑选点
**吸附到最近的候选帧**，容差缺省取「相邻候选帧间距的中位数 / 2」（正好是最近邻的语义
边界）；一个候选帧只被用一次；返回值一定是 `candidates` 的元素，因此
「候选帧 ⊇ 判定通过」这条恒等式不受影响。日志文案同步改为「挑选层吸附到候选帧」。

#### 验证

- 同一 RED 回路对 `p198.mp3` 重跑 → **exit=0（GREEN）**，模型给出 10 条均匀取样、
  `picks=5`。
- `pytest tests/002-video-understanding-sampling tests/008-ocr-assist-and-legacy-cleanup -q`
  → **183 passed**（新增 `test_frame_plan_fallback.py` 8 例 + `test_candidate_frame_snap.py` 6 例）。
- 后端全量 `pytest tests -q` → **666 passed**。

#### 已知残余（与本次改动无关）

`tests/test_task_serial_executor.py::TestTaskSerialExecutor::test_executor_runs_tasks_concurrently`
在全量运行时偶发 `AssertionError: 1 != 2`，单独跑必过。该用例断言两个任务能在
`time.sleep(0.05)` 内被线程池同时接起，是**负载敏感的时序假设**；已用「去掉新测试文件
后仍失败」确认与本次新增测试无关，未在本轮修。
