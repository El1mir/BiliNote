# Specs & Tickets

本目录用于记录**每一项需求**的设计与工单，便于回溯「当时为什么这么改」。

## 约定

```text
specs/
├── README.md                       # 本文件：约定说明
└── <NNN>-<slug>/                   # 一个需求 = 一个目录，NNN 递增
    ├── spec.md                     # 设计规格（背景/目标/决策/接口/测试）
    └── tickets/                    # 工单，按实现顺序编号
        ├── 01-xxx.md
        └── 02-xxx.md
```

## 规则

- **默认在当前 spec 内修正，不新建目录**：只有当 (a) **明确开启一个新需求**，或 (b) **要修正的内容不属于当前 spec** 时，才新建目录。
  bug 修复、决策调整、补测试、实现细节变更等只要**不脱离当前 spec**，就直接改当前 spec。
- **新建目录时**编号 `NNN` 递增（`001`、`002`…），目录名用短横线连接的英文 slug。
- **先写 spec 再写 ticket**：`spec.md` 记录「为什么」和「做成什么样」，`tickets/*.md` 把工作拆成可独立提交/评审的步骤。
- **决策不沉默**：设计中的取舍写进 spec 的「已定决策」；尚未拍板的写进「待确认问题」，不要留成隐含假设。
- **状态标注**：spec 顶部标 `draft` / `approved` / `implemented`。
- 追加到已有 spec 的内容：在 spec 里**注明日期与来源**，并与被修订的既有决策交叉引用（例如「⚠️ 2026-09-26 修订，见 §12」）。

## 索引

| 编号 | 目录 | 状态 | 摘要 |
| --- | --- | --- | --- |
| 001 | [001-bilibili-batch-import](./001-bilibili-batch-import/spec.md) | implemented | B 站合集 / 多P 批量导入（含并发任务隔离） |
| 002 | [002-video-understanding-sampling](./002-video-understanding-sampling/spec.md) | implemented | 视频理解采样方式 + 批量模式融入表单 |
| 003 | [003-openai-compatible-asr](./003-openai-compatible-asr/spec.md) | implemented | OpenAI 兼容 ASR 引擎（替代本地 ASR） |
| 004 | [004-note-math-rendering](./004-note-math-rendering/spec.md) | implemented | 笔记里的 LaTeX 公式渲染（`\(...\)` → `$...$`） |
| 005 | [005-modern-dark-ui-and-task-progress](./005-modern-dark-ui-and-task-progress/spec.md) | **implemented** | 任务阶段协议与前端任务契约（暗色主题随 m02324 已被取代）。2026-10-05 收口：detail dict 贯通、终态阶段归属、任务卡显示阶段与进度、设置页 Prompt 编辑（覆盖层四处落点全部走 `resolve_base_prompt()`）、前端回归测试补齐、`/delete_task` 空壳与非 B 站 downloader 清理。见 spec §12.5。验证：后端 953 passed、前端 78 passed、`tsc -b`/`lint`/`build` 全绿（2026-10-05 合并 `flow/T-012` 到 `master` 后在 master 工作树复跑确认）。 |
| 006 | [006-note-pipeline-performance](./006-note-pipeline-performance/spec.md) | implemented | 笔记生成流水线耗时优化（ASR/拼图/截图并发、下载冗余消除、索引移出关键路径） |
| 007 | [007-note-archive-and-media-cache](./007-note-archive-and-media-cache/spec.md) | implemented | 笔记 ZIP 归档、媒体资源过期清理与视觉图像缓存优化 |
| 008 | [008-ocr-assist-and-legacy-cleanup](./008-ocr-assist-and-legacy-cleanup/spec.md) | implemented | OCR 辅助模式（只有判定通过的帧才编入笔记）+ 删除重新生成与笔记版本管理；⚠️ 2026-10-06 追加 §12.8 提示词全面改写与两处召回缺陷修复 |
| 009 | [009-batch-grouping-and-long-run-robustness](./009-batch-grouping-and-long-run-robustness/spec.md) | implemented | 批量任务每次新建一个组 + 一次 200 个长视频的健壮性（真并发、重启恢复、磁盘门禁、熔断、批量轮询） |
| 010 | [010-group-and-note-deletion](./010-group-and-note-deletion/spec.md) | implemented | 删除分组时二选一（只删组 / 连组内笔记一起删）+ 多选笔记批量删除 + 进行中任务的删除守卫 |
| 011 | [011-failed-task-retry](./011-failed-task-retry/spec.md) | implemented | 失败任务批量重试（按当前可见范围原地重跑，沿用创建时的参数） |
| 012 | [012-rate-limit-backoff](./012-rate-limit-backoff/spec.md) | implemented | 429 退避与停放（全局冷却窗口 5 分钟、单条最长等 1 小时、不判失败、不计熔断） |
| 013 | [013-local-transcriber-hardware-acceleration](./013-local-transcriber-hardware-acceleration/spec.md) | implemented | 本地转写器硬件加速与并行（GPU 默认启用 / CPU 线程数 / 推理并行数） |
| 014 | [014-backend-cache-optimization](./014-backend-cache-optimization/spec.md) | **implemented** | 后端缓存优化（2026-10-14 二审后缩范围）：轮询改为内存字典查找（N=200 实测 stat 1260.8/轮 → 12.4/轮、p50 166.97ms → 5.52ms）、`/task_list` 合并同文件两次读 + 用上已装的 `orjson`（stat 1970.6 → 908.6、p50 162.27ms → 78.80ms；合并读 112.68ms → 60.67ms、orjson 单独 2.93×）、`transcriber_models_status` 目录扫描加 5s TTL（stat 82.4 → 7.0、p50 6.88ms → 1.32ms）。**不引入任何新依赖**。顺带修掉一个既有并发缺陷（`os.replace` 失败时原地覆盖 → 读者读到半截 JSON）。进度：01–06 全部 resolved |
| 015 | [015-note-preset-scene-and-detail](./015-note-preset-scene-and-detail/spec.md) | **implemented** | 笔记预设从 9 个压平的「风格」收敛为**两个正交维度**：场景（生活 / 学术 / 专业）× 详略（精简 / 详细），组合数由「加」改「乘」。删掉后端死代码 `note_styles`（零引用）与提示词里的残留编号（`tutorial` 的「9.」与 `get_toc_format` 的「9.」撞号），请求字段 `style` → `scene` + `detail`，不做老任务兼容（老任务拿到默认 life / detailed）。三端词表由 `backend/tests/015-note-preset-scene-and-detail/test_preset_vocabulary_sync.py` 钉在一起。**二次修订（ticket 04）**：`BASE_PROMPT` 一并重写 —— 修掉它与「篇幅：精简」的对立（「宁可长也不要漏」vs「只写结论层」），补上原本缺失的标题层级约定，并把全部追加片段（format / OCR / LINK / SCREENSHOT）的行首编号去掉。验证：后端 817 passed（基线 777）、web `tsc --noEmit` exit 0 + `pnpm build` 通过 + vitest 30 passed、扩展 `pnpm build` 通过。进度：01–04 全部 resolved |
| 016 | [016-web-startup-optimization](./016-web-startup-optimization/spec.md) | **implemented** | Web 启动改为单控制台并行拉起后端/Vite，健康检查通过后再开浏览器；避免启动时加载 ChromaDB/RAG。实测 `import main` 5.6–6.3s → 4.3s，启动器双服务 ready 6.14s；后端 818 passed。 |
| 017 | [017-web-rebuild-and-architecture](./017-web-rebuild-and-architecture/spec.md) | **implemented** | 网页优先的 Ember Studio 全面重构：中英文 i18n、三端响应式、Bilibili-only 生成、前后端同步接口与性能预算。 |
| 018 | [018-single-batch-and-merged-note](./018-single-batch-and-merged-note/spec.md) | **implemented** | 单集/批量分离（单集粘贴多P 自动切批量并展开——用户报的 BV1RPC1BbEVN 实测 52 个分P）+ 批量列表序号范围选择 + 「合并任务」把多条视频笔记合成**一条**任务笔记（默认结构拼接，可选模型润色，部分失败保留成果）。顺带修掉重构时删掉的 `parseRangeSelection` / `normalizeMathDelimiters` / `toPercent` / `isTaskInFlight` 四个 util（对应 001/004/005/010 的测试一直是红的）。验证：后端 917 passed、前端 34 passed、`tsc -b`/`build`/`lint` 全绿、Playwright 实测 tab 切换与合并开关。 |
| 019 | [019-global-model-in-provider-section](./019-global-model-in-provider-section/spec.md) | **implemented** | 全局模型从通用设置搬到「AI 模型设置（模型提供商）」页顶部，候选**只列启用供应商下**的模型，选中即保存；通用设置里这一项整个删掉。同时修掉「模型在供应商里已删、设置页仍显示旧名字」——读路径校验（供应商仍启用 + 模型仍存在）+ 删模型时主动清指针，两处兜底。验证：后端 925 passed（新增 6 例，同步 013 文案与 009 fixture）、前端 38 passed + `tsc -b`/`lint`/`build` 全绿、headless Chromium 实测 6 步（含「删掉全局模型后顶部回到未激活」）。 |
| 020 | [020-note-rendering-and-batch-options](./020-note-rendering-and-batch-options/spec.md) | **implemented** | 笔记数学渲染修复 + 批量生成设置 + 分组区滚动 + 提示词图片保留。①分组列表固定 264px 高在 900px 窗口把最后一行切一半 → 改 `max-h-[min(45vh,420px)]` + `overscroll-contain` + section `shrink-0`；②`BatchImportPanel` 原来完全没有设置 UI → 抽 `GenerationOptions` 受控组件，单集/批量共用（`generationSettings.ts` 放类型/默认值/`toPayloadSettings`）；③用户那篇笔记 169 个公式 KaTeX 全合法，坏在 remark-math 对「`$$` 与内容同行」解析失败 + 旧逐行转换器处理不了跨行 `\[…\]` → 规范化改为围栏分段整体处理，KaTeX 关 `throwOnError`；④`BASE_PROMPT` 补「图片里的题目/板书/表格原样保留、不改写不讲解」+ 公式分隔符规则。验证：后端 929 passed、前端 48 passed、`tsc -b`/`lint` 干净、浏览器实测三项（滚动 / 批量设置 / 用户笔记渲染 0 error）。 |
