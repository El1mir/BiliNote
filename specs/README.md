# Specs & Tickets

本目录用于记录**每一项需求**的设计与工单，便于回溯「当时为什么这么改」。

## 约定

```
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
| 005 | [005-modern-dark-ui-and-task-progress](./005-modern-dark-ui-and-task-progress/spec.md) | partial | 任务阶段协议与前端任务契约（后端齐备、工单 07 已完成；暗色主题随 m02324 已被取代；前端阶段展示残余缺陷见 spec §12） |
| 006 | [006-note-pipeline-performance](./006-note-pipeline-performance/spec.md) | implemented | 笔记生成流水线耗时优化（ASR/拼图/截图并发、下载冗余消除、索引移出关键路径） |
| 007 | [007-note-archive-and-media-cache](./007-note-archive-and-media-cache/spec.md) | implemented | 笔记 ZIP 归档、媒体资源过期清理与视觉图像缓存优化 |
| 008 | [008-ocr-assist-and-legacy-cleanup](./008-ocr-assist-and-legacy-cleanup/spec.md) | implemented | OCR 辅助模式（只有判定通过的帧才编入笔记）+ 删除重新生成与笔记版本管理；⚠️ 2026-10-06 追加 §12.8 提示词全面改写与两处召回缺陷修复 |
| 009 | [009-batch-grouping-and-long-run-robustness](./009-batch-grouping-and-long-run-robustness/spec.md) | implemented | 批量任务每次新建一个组 + 一次 200 个长视频的健壮性（真并发、重启恢复、磁盘门禁、熔断、批量轮询） |
| 010 | [010-group-and-note-deletion](./010-group-and-note-deletion/spec.md) | implemented | 删除分组时二选一（只删组 / 连组内笔记一起删）+ 多选笔记批量删除 + 进行中任务的删除守卫 |
| 011 | [011-failed-task-retry](./011-failed-task-retry/spec.md) | implemented | 失败任务批量重试（按当前可见范围原地重跑，沿用创建时的参数） |
| 012 | [012-rate-limit-backoff](./012-rate-limit-backoff/spec.md) | implemented | 429 退避与停放（全局冷却窗口 5 分钟、单条最长等 1 小时、不判失败、不计熔断） |
| 013 | [013-local-transcriber-hardware-acceleration](./013-local-transcriber-hardware-acceleration/spec.md) | implemented | 本地转写器硬件加速与并行（GPU 默认启用 / CPU 线程数 / 推理并行数） |
