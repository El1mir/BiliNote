# 005 · 现代暗色核心界面与任务阶段进度

- **状态**：implemented（残余缺陷已于 2026-10-05 收口，见 §12.5）
- **日期**：2026-09-26
- **范围**：后端任务阶段协议、任务轮询日志降噪、Web 核心页面暗色重构
- **上游**：001 / 002 / 003 / 004

## 1. 背景

当前前端进度条只有少量固定步骤，而后端生成笔记是长流水线：解析、字幕获取、媒体下载、转写、视频理解采样、抽帧、拼图、模型总结、后处理和保存。大量耗时过程被折叠到少数状态中，用户无法判断任务是否仍在运行、卡在哪一步或下一步是什么。

同时，前端每隔几秒请求一次 `/api/task_status/{task_id}`，Uvicorn access logger 会把每个成功轮询请求以 INFO 打印，长任务期间会产生大量重复日志，掩盖真正有价值的业务日志。

现有前端已经使用 Tailwind、Radix primitives、部分 shadcn 风格组件和 `lucide-react`，但页面视觉仍不统一，主要页面需要统一为暗色紫红工作台。

## 2. 目标

1. 建立与后端实际流水线对应的任务阶段协议，支持阶段状态、阶段内进度和可读详情。
2. 保留旧 `status` 字段和现有 API 语义，新增字段向后兼容，不破坏历史任务、配置和已有调用方。
3. 降低成功状态轮询的 Uvicorn 控制台噪声，保留异常请求和业务阶段日志。
4. 在 Web 端重构首页工作台、任务队列、任务详情、笔记查看和设置页，最大程度保留当前功能。
5. ~~采用暗色为唯一主题，使用紫红作为品牌与交互主色，并允许扩展状态色、透明度和明暗阶。~~
   **⚠️ 2026-10-05 已取代**：用户 m02324 明确「浅色 DesignMD 是最终意图」。详见 §12。

## 3. 非目标

- 不重写浏览器扩展独立 UI。
- 不重写 Tauri 原生窗口、菜单或打包流程。
- 不破坏已有 API、任务缓存、配置数据和路由。
- 不用估算值伪造精确百分比；无法准确计算的阶段显示活动状态和详情。
- 不引入与现有 Tailwind/Radix/lucide 能力重复的大型 UI 框架。

## 4. 已定决策

| # | 决策 | 结论 |
|---|---|---|
| 1 | 进度实现范围 | 同时改造后端阶段协议与前端展示，前端不只做旧状态映射 |
| 2 | 后端阶段粒度 | 覆盖完整流水线：排队、解析、字幕、下载、转写、采样、抽帧、拼图、总结、后处理、保存、完成/失败 |
| 3 | 兼容方式 | 保留原 `status`；新增 `stage`、`stage_label`、`progress`、`stage_progress`、`message`、`detail`、`updated_at` |
| 4 | 进度真实性 | 只有有可靠分母的步骤显示确定百分比；模型调用等不可预测步骤显示活动状态 |
| 5 | 轮询日志 | 成功的 `/api/task_status/{task_id}` 轮询请求不打印 Uvicorn access INFO；非 2xx 保留 |
| 6 | UI 范围 | Web 核心页面：首页工作台、任务详情/历史、笔记查看、设置页及启动/错误/空状态 |
| 7 | 主题 | 仅暗色主题，不实现明暗切换 |
| 8 | 颜色 | `#780018`、`#AA0033`、`#CC0044`、`#2B2B2B`、`#4A4A4A`、`#1A1A1A`、`#6B6B6B` 为基准，可扩展辅助色和状态色 |
| 9 | 组件 | 优先复用现有 shadcn/Radix 风格组件和 `lucide-react` |

## 5. 阶段协议

状态文件和任务状态接口继续返回旧字段，并在处理中和终态返回以下字段：

```json
{
  "status": "TRANSCRIBING",
  "stage": "transcribing",
  "stage_label": "音频转写",
  "progress": 43,
  "stage_progress": 68,
  "message": "正在处理第 7 / 16 个音频片段",
  "detail": {
    "current": 7,
    "total": 16,
    "unit": "chunks"
  },
  "updated_at": "2026-09-26T14:11:33Z"
}
```

标准阶段及后端责任：

| stage | label | 责任 |
|---|---|---|
| `queued` | 排队中 | 任务进入执行队列 |
| `parsing` | 解析链接 | 初始化下载器、模型和任务上下文 |
| `fetching_subtitles` | 获取字幕 | 读取缓存或平台字幕，判断是否需要转写 |
| `downloading_video` | 下载视频 | 为截图或视频理解下载视频 |
| `downloading_audio` | 下载音频 | 下载音频或提取音频元信息 |
| `transcribing` | 音频转写 | ASR、音频切片、字幕缓存 |
| `planning_frames` | 规划采样 | 高价值采样、综合采样、LLM 选帧 |
| `extracting_frames` | 抽取画面 | 从视频抽取选定时间点的帧 |
| `building_grids` | 拼接网格图 | 生成多帧网格图 |
| `summarizing` | 生成总结 | 调用模型生成 Markdown 笔记 |
| `post_processing` | 整理内容 | 插入截图、链接和格式化内容 |
| `saving` | 保存结果 | 写入结果文件和数据库 |
| `success` | 已完成 | 任务完成 |
| `failed` | 失败 | 任务失败并提供错误信息 |

`progress` 表示全局进度，`stage_progress` 表示当前阶段进度。二者可以为 `null`；前端对 `null` 显示活动指示器而不是伪造数值。阶段权重由后端统一定义，前端不自行估算。

## 6. 日志规则

- 为 Uvicorn access logger 增加针对任务状态轮询路径的过滤器。
- `GET /api/task_status/<task_id>` 返回 2xx 时不输出 access INFO。
- 该路径返回 4xx/5xx 时保留 access WARNING/ERROR 或等价记录。
- 其他请求的 access 日志行为不变。
- 应用层只在阶段变化、阶段完成、失败和完成时记录关键业务日志，不为每次轮询记录业务日志。

## 7. 前端设计范围

### 首页工作台

- 暗色工作台布局，保留生成表单、批量导入、任务队列、历史入口。
- 任务卡片显示当前阶段、全局进度、阶段进度、耗时、详情和错误状态。
- 长任务显示可滚动阶段时间线，当前阶段有活动指示器，已完成阶段可回看详情。
- 保留重试、删除、打开笔记、查看转写等已有操作。

### 笔记查看

- 保留 Markdown、LaTeX、截图、视频链接、转写、对话和 Markmap 功能。
- 统一暗色内容区、工具栏、标签、侧栏和错误/空状态。

### 设置页

- 保留模型、下载器、转写、Prompt、监控、关于等配置功能。
- 统一导航、表单、输入、选择器、开关、提示和保存反馈。

## 8. 测试与验收

### 后端

- 旧客户端只读取 `status` 时行为不变。
- 新字段在每个标准阶段正确写入并通过 `/task_status` 返回。
- 失败任务包含可读错误信息和最后阶段。
- 状态轮询 2xx 不刷 access INFO，异常状态仍可追踪。
- 并发任务之间状态文件不互相覆盖。

### 前端

- 全站核心页面使用暗色设计 token，不出现亮色旧页面混杂。
- 任务阶段与后端协议一致，刷新页面后仍能恢复任务进度。
- 长阶段无确定百分比时不会显示虚假的数值进度。
- 现有生成、批量、笔记查看、设置、重试和删除功能保持可用。
- `pnpm test`、`pnpm build` 通过；关键页面完成桌面和窄屏检查。

## 9. 实现清单

| # | 工单 | 状态 |
|---|---|---|
| 01 | 后端任务阶段模型与兼容状态文件 | 已完成 |
| 02 | 任务状态接口扩展与阶段权重 | 已完成 |
| 03 | Uvicorn 状态轮询日志过滤 | 已完成 |
| 04 | 下载、字幕、转写流程进度埋点 | 已完成 |
| 05 | 采样、抽帧、拼图流程进度埋点 | 已完成 |
| 06 | 总结、后处理、保存流程进度埋点 | 已完成 |
| 07 | 前端任务类型、轮询和持久化适配 | 已完成 |
| 08 | 前端阶段时间线与进度组件 | 已完成（2026-10-05 收口） |
| 09 | 暗色设计 token 与基础组件统一 | 已被取代（2026-10-05） |
| 10 | 首页任务队列信息密度 | 已完成（2026-10-05 收口） |
| 11 | 设置页 Prompt 页面缺失 | 已完成（2026-10-05 收口） |
| 12 | 前端回归测试 | 已完成（2026-10-05 收口） |
| 13 | 修复 note.py 日志丢失（未接入统一 logger） | 已完成 |
| 14 | 任务 ID 贯穿全流程（修复幻影状态文件与 90% 冻结） | 已完成 |
| 15 | 转写进度回调接线与阶段明细 | 已完成 |
| 16 | 进度停滞可见性（耗时与最后更新时间） | 已完成 |

## 10. 待确认问题

无。范围已于 2026-09-26 确认。

## 11. 2026-09-26 修订：实机排查发现的进度缺陷

⚠️ 本节由一次真实任务排查（BV1E7wtzaEdq，用户反馈「前端卡在 99」）追加，
修订并补漏 §5 阶段协议与 ticket 04/06 的进度埋点。新增工单见 `tickets/13`–`16`。

发现的问题：

1. `note.py` 使用裸 `logging.getLogger(__name__)`（无 handler），
   所有模块级 INFO 里程碑日志被丢弃，失败日志无前缀 → ticket 13。
2. `_summarize_text()` 用 `markdown_cache_file.stem` 反推 task_id，把状态写进了
   `note_results/<task_id>_markdown.status.json`（幻影任务），
   导致整个总结阶段真实状态文件不再更新、前端冻结在 90%（本次实测 90% 停留 22 分钟）→ ticket 14。
3. `_transcribe_audio()` 在调用 `transcriber.transcript()` **之后**才安装 `progress_callback`，
   ticket 04 的转写进度埋点实际从未生效 → ticket 15。
4. `saving` 阶段（99%）本身是「结果落盘 + 数据库写入」的合法长阶段，
   但前端只有绝对时间、看不出是否停滞 → ticket 16。

结论：进度「卡住」既可能是真的卡住，也可能是状态写错文件；
本次同时修掉两者，并为「长时间无状态更新」补前端可见性。


## 12. 2026-10-05 收口：主题决策变更与残余缺陷

⚠️ 本节把 spec 005 从「全量 approved」重新定级为 **partial**。触发原因是用户 m02324 的决定，
以及一次对工单 07–12 的逐条只读核查。

### 12.1 主题决策变更

用户 m02324 明确：**浅色 DesignMD 是最终意图**（不再走「暗色紫红为唯一主题」）。

因此 §4 决策 7/8 与工单 09 整体作废。下列曾经被记为缺陷的现象**不再算缺陷**：

- `BillNote_frontend/src/index.css:209–275` 的 `:root` 块用 `!important` 覆盖紫红 token —— 那是浅色方向。
- `#6B6B6B` 只作 `index.css:169` 的字面量、从未成为 token —— 浅色方向不需要它。
- `src/components/ui/` 下 17 个组件的 `dark:` 变体永不激活 —— 浅色方向不需要它们激活。
- 焦点环是 `#3B82F6` 而非品牌紫红 —— 浅色方向下这是正确的。
- `MarkdownViewer` 引 `github-markdown-light.css`、`ChatPanel` 的 `bg-blue-500`、
  `transcriptViewer` 的 `bg-white`、`SettingLayout` 的 `bg-white` 等 —— 都是浅色，正是选定方向。

### 12.2 逐工单结论

| 工单 | 结论 | 依据 |
| --- | --- | --- |
| 07 | **已完成** | 三条验收均有实现，落点见 `tickets/07-frontend-task-contract.md` 的「完成情况」 |
| 08 | ~~待实现（遗留缺陷）~~ → **已完成（2026-10-05 收口）** | 原 6 条缺陷落点见 §12.5；原记录见 `tickets/08-progress-timeline.md` |
| 09 | **已被取代** | 随 m02324 整体作废，见 `tickets/09-dark-theme-foundation.md` |
| 10 | ~~待实现（遗留缺陷）~~ → **已完成（2026-10-05 收口）** | 原 4 条缺陷落点见 §12.5；原记录见 `tickets/10-home-workbench-redesign.md` |
| 11 | ~~待实现（遗留缺陷）~~ → **已完成（2026-10-05 收口）** | Prompt 页已挂进 `SettingsPage.tsx`，落点见 §12.5；原记录见 `tickets/11-note-and-settings-redesign.md` |
| 12 | ~~待实现（遗留缺陷）~~ → **已完成（2026-10-05 收口）** | 前后端测试已补齐，落点见 §12.5；原记录见 `tickets/12-regression-and-visual-acceptance.md` |

### 12.3 最要紧的三条

如果只修三条，按这个顺序：

1. **`detail` 永远不显示** —— 后端写的全是 dict，前端 `utils/text.ts:12-20` 的 `asText` 对对象返回 `''`。
   所有阶段详情被静默吞掉，且类型声明（`taskStore/index.ts:129` 的 `string | null`）与实现不符。
2. **成功时 12 个阶段全显示为待处理** —— `services/note.py:592` 写 `stage='success'`，
   而 `ProgressTimeline.tsx:49-62` 的 stages 列表里没有 `success`。
   失败时同理（`services/note.py:600` 未传 `stage`），失败阶段被覆盖，没有阶段标红。
3. **任务卡片只有 legacy 徽标** —— `NoteHistory.tsx:206-216`。整个 `src/pages` 里
   `stage`/`progress`/`message`/`detail`/`updatedAt` 的唯一消费者是 `ProgressTimeline.tsx`。

### 12.4 非目标（本次收口刻意不做）

- 不重命名 spec 005 目录或标题。目录名里的「dark-ui」已是历史名词，改名会让所有既有引用失效。
- 不动 `index.css:209–275`。它是浅色方向的实现，不是死代码。
- 不补前端测试。那正是工单 12 的内容。

### 12.5 2026-10-05 收口结果

§12.2 / §12.3 列的遗留缺陷已全部实现，本节记录落点，供后续回归时对照。

| 原缺陷 | 修复落点 |
| --- | --- |
| `detail` 永远不显示（工单 08 缺陷 1） | 后端 `app/services/task_read_model.py` 新增 `detail_payload()`：dict 透传、JSON 字符串解一次、其它字符串包成 `{'text': ...}`；`TaskView.detail` 改为 `dict[str, Any] \| None`。前端 `utils/taskStatus.ts` 的 `TaskDetail = Record<string, unknown>` + `toDetailPayload()`，`taskStore/index.ts` 同步把 `detail` 从 `string \| null` 改掉；`taskState.ts` 的 `detailSummary()` 负责渲染切片数 / 帧数 / 网格数。 |
| 成功时 12 个阶段全显示待处理（工单 08 缺陷 2/3） | `task_read_model.py` 的 `_PHASE_ALIASES` 删掉 `"success": "finalizing"`，`normalize_phase` 在缺阶段时按终态落 `success` / `failed`；`services/note.py` 新增 `_read_recorded_stage()` + `_resolve_stage()`，终态继承最后一次在途阶段，失败时能定位到断在哪一步。前端 `taskState.ts` 的 `stageKey()` 认得 `success` / `failed`，认不出返回 `null` 由调用方回落状态文案。 |
| 任务卡片只有 legacy 徽标（工单 08 缺陷 4） | 新增 `ember/features/workspace/TaskCard.tsx`，卡片上渲染阶段、阶段进度与详情计数；`TaskList.tsx` 改用它。 |
| 设置页无 Prompt 页面（工单 11 残余） | 后端：`general_settings` 新增 `base_prompt_override` 列 + `normalize_base_prompt_override()`（必须含 `video_title` / `segment_text` / `tags` 三个占位符、上限 20000 字符，否则判无效回落空串）+ `routers/general.py` 的字段透传；`runtime_limits.base_prompt_override()` 走 5 秒缓存读取，`gpt/prompt_builder.py` 的 `resolve_base_prompt()` 统一对外。**五个消费者**（`generate_base_prompt` 与 `deepseek_gpt.py` / `openai_gpt.py` / `qwen_gpt.py` 三个适配器）全部改为 `resolve_base_prompt().format(...)`，否则改设置页只对三分之一 provider 生效。前端：新增 `ember/pages/settings/sections/PromptSection.tsx` 并挂进 `SettingsPage.tsx` 的 `prompt` 路由。 |
| 前端回归测试几乎空白（工单 12） | `BillNote_frontend/tests/005-modern-dark-ui/` 现有 `taskStatus.test.ts`（两套命名双写、`toDetailPayload` 拒收非 dict）、`taskState.test.ts`（未知阶段回退、`progress === null` 不伪造）、`taskProgressCard.test.tsx`（进度卡五种渲染）、`taskCard.test.tsx`（列表卡）；后端 `tests/005-modern-dark-ui-and-task-progress/` 补 `test_terminal_stage_attribution.py` 与 `test_base_prompt_override.py`。 |

同时清理的死代码：`routers/note.py` 的 `/delete_task` 空壳路由与 `RecordRequest`；非 B 站 downloader（`youtube` / `douyin` / `kuaishou` / `xiaoyuzhoufm` / `local`）连同 helper 目录一并删除，`SUPPORT_PLATFORM_MAP` 只剩 B 站。

闸门实测（2026-10-05，在 `flow/T-012` 合入 `master` 之后的 master 工作树复跑）：后端 `pytest` **953 passed, 1 warning, 15 subtests passed**（收口前 934，新增 19 条全是本批用例）；前端 `pnpm test` 14 文件 / 78 用例、`tsc -b`、`pnpm lint`、`pnpm build`（built in 24.50s，仅 markdown chunk 795.41 kB 的体积告警）全部 exit 0；`scripts/i18n-contract.cjs` 报 "501 keys, zh-CN and en-US aligned"。

分支落地（2026-10-05）：工单 08/10/11/12 与死代码清理的四个提交 `49522d7` / `6538a41` / `9b81067` / `442ecbf` 原本只落在 `flow/T-012`，以 `git merge --ff-only flow/T-012` 快进并入 `master`（merge-base `7471c35`，无冲突、不 squash，保留四个独立提交），此后 `git merge-base --is-ancestor 442ecbf master` 为 true。
