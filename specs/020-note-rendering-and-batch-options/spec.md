# 020 · 笔记渲染、批量生成设置与分组区滚动

- 状态：implemented
- 日期：2026-10-18
- 来源：用户 round-1 反馈（四点，见 §1）
- 关联：018（单集/批量分离与合并任务）、015（笔记预设场景 × 详略）、004（数学渲染首次实现）

## 1. 背景

用户一次性报了四个问题，前三个是缺陷，第四个是提示词缺失：

1. **分组区滚不动**：工作区右栏「分组」列表写死 `max-h-[264px]`。用户真实数据是 14 个分组（必修三物理 51 篇 / 解析几何 30 篇 + 12 个临时组），900px 高的窗口里第 10 行正好被裁掉一半，右侧滚动条细到看不见 —— 视觉上就是「只能看到一个分组和未分组」。
2. **批量页调不了生成设置**：`BatchImportPanel.tsx` 里根本没有设置 UI，只有写死的 `DEFAULT_PROFILE`；「生成设置」折叠面板只长在 `IntakeForm`（单集）里。批量用户无法改质量 / 场景 / 详略 / 输出内容 / 画面理解。
3. **数学笔记「全是红色、行内公式没渲染」**：用户贴的笔记是 `note_results/813f0e30-…_markdown.md`（343 行，`$` 442 个、`$$` 104 个、`\begin{cases}` 2 处）。两个独立成因：
   - 用 katex 0.16.40 对这 169 个 `$`/`$$` span 逐个 `renderToString({throwOnError:true})` → **0 error**，公式本身合法；坏在 **remark-math 对「`$$` 与内容同行、闭符号在末行」的块公式解析失败**：整段退化成文本，后面的 `$$` 两两错位，有的片段被当成 math 解析后报错（KaTeX 红字），大量行内 `$…$` 因此没被识别。
   - 另一篇 `cdacce16-…`（490 个公式）全用 LaTeX 原生 `\(…\)` / `\[…\]`，且 `\[…\]` 多数跨行。旧的 `normalizeMathDelimiters` 是**逐行**正则，跨行的 `\[…\]` 永远匹配不到 → 原样输出。
4. **基础提示词缺图片保留约束**：用户要求「尽可能保留图片内容（如题目）和布局，图片里的题目不要改写或讲解，原样保留信息」。

## 2. 目标

- 分组列表在分组多时可滚动、高度跟随视口，最后一行不再被裁成半行。
- 批量生成面板有与单集一致的「生成设置」，并且两处共用同一份实现（以后加参数不会只加一半）。
- 数学笔记在**不重新生成**的前提下正确渲染（前端规范化兜底），同时提示词约束新笔记的输出格式。
- 基础提示词明确「图片里的题目原样保留、不改写不讲解」。

## 3. 非目标

- 不重写笔记阅读器的排版体系。
- 不为老笔记做数据迁移（渲染修复走读路径，老笔记刷新即生效）。
- 不改后端生成接口的请求/响应契约（本次没有新增字段）。

## 4. 已定决策

| # | 决策 | 理由 / 代价 |
| --- | --- | --- |
| 1 | 数学分隔符规范化放在**前端读路径**（`normalizeMathDelimiters`），不靠模型每次都写对 | 老笔记立刻可读；代价是每次渲染多一遍字符串处理（毫秒级） |
| 2 | 规范化改为「按代码围栏分段、段内整体处理」，并额外处理 `$$` 与内容同行的情况 | 逐行正则处理不了跨行块；围栏分段保证代码块里的 `$` 不被误改 |
| 3 | KaTeX 关闭 `throwOnError`（`{ throwOnError: false, strict: false }`） | 单个坏公式不该炸整篇；坏公式原地标红，其余照常渲染 |
| 4 | 提示词同时约束输出格式：行内只写 `$…$`、独立公式用 `$$` 且**必须单独占一行**、禁止 `\(…\)` / `\[…\]` | 双保险：新笔记从源头就写对，减少前端规范化的工作量 |
| 5 | 生成设置抽成受控组件 `GenerationOptions`，类型/默认值/折算放 `generationSettings.ts` | 单集与批量渲染同一个面板；组件文件只导出组件（react-refresh 约束） |
| 6 | 批量默认格式仍是 `['toc','link','summary']`（单集默认 `[]`） | 批量通常要一份能直接读的成品；保持既有行为不变 |
| 7 | 分组列表高度 `max-h-[min(45vh,420px)]` + `overscroll-contain`，section 加 `shrink-0` | 视口自适应，且滚动不会把整页一起带走 |
| 8 | 图片保留约束写进 `BASE_PROMPT` 的「画面内容」节 | 所有场景（生活/学术/专业）都生效，而不是只影响截图格式 |

## 5. 接口与契约

后端 API 无变化。变化的是**提示词文本**与前端组件契约：

```ts
// BillNote_frontend/src/ember/features/workspace/generationSettings.ts
export type GenerationSettings = {
  quality: 'fast' | 'medium' | 'slow'
  scene: string
  detail: string
  format: string[]
  extras: string
  video_understanding: boolean
  video_interval: number
  sampling_mode: 'interval' | 'smart' | 'hybrid'
  max_frames: number
  frames_per_second: number
  frame_limit_mode: 'total' | 'per_second'
  ocr_assist: 'global' | 'on' | 'off'   // UI 三态
  grid_size: [number, number]
}
export const DEFAULT_GENERATION_SETTINGS: GenerationSettings
/** UI 三态 → 接口契约：global→null（跟随全局）、on→true、off→false */
export const toPayloadSettings: (s: GenerationSettings) => { … ocr_assist: boolean | null }

// BillNote_frontend/src/ember/features/workspace/GenerationOptions.tsx
export function GenerationOptions(props: {
  value: GenerationSettings
  onChange: (patch: Partial<GenerationSettings>) => void
  idPrefix?: string   // 'single' / 'batch'，避免同页两份面板的 input id 冲突
}): JSX.Element
```

提示词新增/修改（`backend/app/gpt/prompt.py`，`BASE_PROMPT`）：

- 写作原则第 5 条拆成三条子项：行内 `$…$`；独立公式 `$$` 单独占行；下标/上标/括号写准。
- 画面内容节新增：题目 / 选项 / 板书 / 表格**原样保留**，不改写、不翻译、不讲解、不替读者总结；引用了截图就保留截图，不要只用一句话概括。

## 6. 实现要点

### 6.1 数学渲染（`BillNote_frontend/src/utils/markdown.ts`）

三段式：

1. `isolateDollarFences`：把 `$$x$$`（同行闭合）以及「`$$` 与内容同行、闭符号在末行」的块拆成 `$$` / 正文 / `$$` 三行；句子中间的 `$$…$$` 也拆成块。
2. `convertProse`：`\[…\]` → 前后带空行的 `$$` 块（支持跨行）；`\(…\)` → `$…$` 并把 body 内换行折成空格。
3. `normalizeMathDelimiters`：用 `FENCE_RE` 跟踪三反引号/波浪号围栏，非围栏段落整体 flush 转换；围栏内原样保留。

`MarkdownNote.tsx` 的 `rehypePlugins` 由 `[rehypeKatex, rehypeSlug]` 改为 `[[rehypeKatex, { throwOnError: false, strict: false }], rehypeSlug]`。

### 6.2 生成设置共享（前端）

- `generationSettings.ts`：类型 + 默认值 + `toPayloadSettings`（纯函数，可单测）。
- `GenerationOptions.tsx`：受控面板，含质量/场景/详略 Select、格式 Chip、补充要求 Textarea、画面理解 Switch、抽帧方式 Tabs、间隔 / 上限 / fps / 宫格 / OCR。
- `IntakeForm`：`useWatch` 组出 `settings`，`applySettings(patch)` 逐个 `form.setValue(..., { shouldDirty: true })` 写回；面板 JSX 由 250 多行内联换成一行组件。
- `BatchImportPanel`：`BATCH_DEFAULT_SETTINGS = { ...DEFAULT_GENERATION_SETTINGS, format: ['toc','link','summary'] }`，picking 阶段在「合并任务」卡之前加「生成设置」折叠按钮（`aria-expanded` + `workspace.form` 文案），提交走 `buildBatchPayload(toPayloadSettings(settings), …)`。

### 6.3 分组区滚动（`GroupPanel.tsx`）

- `<section>` 加 `shrink-0`（rail 是 flex 列，不加会被下面的 TaskList 压扁）。
- 列表容器 `max-h-[264px]` → `max-h-[min(45vh,420px)]`，并加 `overscroll-contain`。

## 7. 测试要点

后端 `backend/tests/020-note-rendering-and-batch-options/test_prompt_format_rules.py`（4 例）：

1. `BASE_PROMPT` 里出现「必须单独占一行」的公式规则文案；
2. 明确禁止 `\(…\)` / `\[…\]` 两种 LaTeX 原生分隔符；
3. 出现「原样保留」且禁止「改写 / 讲解」的图片约束；
4. `BASE_PROMPT` 仍只有 `video_title` / `tags` / `segment_text` 三个占位符且可 `format`（防止改文案时把占位符写坏）。

前端 `BillNote_frontend/tests/020-note-rendering-and-batch-options/`：

- `markdown.test.ts`（6 例）：跨行 `\[…\]` 转 `$$` 块；`$$` 与内容同行拆行；「开符号同行 + 闭符号末行」的 cases 块；行内 `$…$` 不动；跨行 `\(…\)` 折单行；代码围栏内 `$$` 不动。
- `generationSettings.test.ts`（4 例）：默认值字段齐；OCR 三态折 `true/false/null`；其余设置透传；批量请求体带设置且合并时不带 `group_name`。

回归：`tests/004-note-math-rendering/math.test.ts` 的「已经是 `$…$` 原样返回」用例改成只含行内公式（原用例含 `$$y = x$$`，新规则会把它拆行）。

## 8. 实现清单

| # | 文件 | 改动 |
| --- | --- | --- |
| 1 | `BillNote_frontend/src/utils/markdown.ts` | 重写为围栏分段 + 整体转换，新增 `isolateDollarFences` / `convertProse` |
| 2 | `BillNote_frontend/src/ember/features/reader/MarkdownNote.tsx` | `rehype-katex` 传 `{ throwOnError: false, strict: false }` |
| 3 | `BillNote_frontend/src/ember/features/workspace/generationSettings.ts` | 新建：类型 / 默认值 / `toPayloadSettings` |
| 4 | `BillNote_frontend/src/ember/features/workspace/GenerationOptions.tsx` | 新建：受控设置面板（`idPrefix` 支持同页两份） |
| 5 | `BillNote_frontend/src/ember/features/workspace/IntakeForm.tsx` | 内联面板换成共享组件；`useWatch` + `applySettings` |
| 6 | `BillNote_frontend/src/ember/features/workspace/BatchImportPanel.tsx` | 新增「生成设置」折叠区 + `settings` state；提交走 `toPayloadSettings` |
| 7 | `BillNote_frontend/src/ember/features/workspace/GroupPanel.tsx` | `shrink-0` + `max-h-[min(45vh,420px)]` + `overscroll-contain` |
| 8 | `backend/app/gpt/prompt.py` | 公式格式三条子项 + 图片原样保留两条 |
| 9 | `backend/tests/020-…/test_prompt_format_rules.py` | 新建 4 例 |
| 10 | `BillNote_frontend/tests/020-…/{markdown,generationSettings}.test.ts` | 新建 10 例 |
| 11 | `BillNote_frontend/tests/004-note-math-rendering/math.test.ts` | 用例改为只含行内公式 |
| 12 | `specs/README.md` | 索引新增 020 |

## 9. 验证记录（2026-10-18）

| 项 | 结果 |
| --- | --- |
| `backend: pytest -q` | **929 passed**（020 新增 4 例） |
| `backend: pytest tests/015-note-preset-scene-and-detail` | 54 passed（提示词改写的回归面） |
| `frontend: pnpm exec tsc -b` | exit 0 |
| `frontend: pnpm lint` | 0 error 0 warning |
| `frontend: pnpm exec vitest run` | **10 files / 48 tests passed** |
| 浏览器：分组滚动 | 14 个分组时列表 `scrollHeight 494 / clientHeight 380`，`scrollTop` 可设到 114（= max）；滚到底可见 `zzscroll12` 与「未分组」；截图 `s020-groups-scrolled.png` |
| 浏览器：批量生成设置 | 批量 tab 解析 `BV1RPC1BbEVN`（52 个分P）进入 picking 阶段后出现「生成设置」，展开后 id 为 `batch-quality` / `batch-scene` / `batch-detail`（单集是 `single-*`）；把质量改「高质量」后重渲染仍是 `slow`；打开「画面理解」后出现抽帧方式 / 抽帧间隔 / 宫格尺寸 / OCR 辅助；截图 `s020-batch-settings2.png` |
| 浏览器：数学笔记渲染 | 用真实组件 `MarkdownNote` 渲染用户那篇笔记（`813f0e30-…`）：`katex` 169 个、`katex-error` **0** 个、`katex-display` 52 个、正文残留 `$` **0**；`\begin{cases}` 渲染成带大括号的方程组；截图 `s020-math-render.png` |
| 清理 | 12 个临时分组 `zzscroll1..12` 已删，真实分组「必修三物理(51)」「解析几何(30)」保留 |

## 10. 取舍与遗留

- 用户那篇笔记的 169 个公式**本身合法**，所以本次不追求「公式更漂亮」，只解决「解析错位导致整段退化成文本」。若模型写出真正非法的公式，现在会被 KaTeX 原地标红而不是整篇白屏。
- 批量面板的「生成设置」只在 **picking 阶段**出现（解析出分集之后），因为输入阶段还没有任何可生成的条目；用户从单集自动切到批量时也一样。
- 分组列表滚到底时最后一行仍可能被裁一半（滚动容器的固有表现），但已有明显滚动条且能滚到底；如果以后要完全避免，需要改成虚拟列表或分页。
- 提示词只影响**新生成**的笔记；老笔记靠前端规范化兜底（已验证）。
