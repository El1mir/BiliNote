# UI 合理性改进计划 — BiliNote Web 前端逐符号审计

> 依据：ui-ux-pro-max / apple-design（流体界面）/ emil-design-eng 三套设计知识。
> 审计对象：`BillNote_frontend/src`（Ember Studio 表现层）。
> 方式：逐符号读源码 + 机器可算事实（对比度脚本、grep 计数）。**每条结论均带 文件:行号 + 层级 + 规则编号。**
> 状态：`rev 6` —— Q1–Q8 与人的 4 项取舍已裁决、scope 逐文件收敛；A7 缺陷判定已撤销。**本卡不改产品代码**，W0–W5 由调度拆卡分派。
> 日期：2026-11-10 · 分支 flow/T-057

---

## 0. 结论先行

基础层（motion / tokens / 按压反馈 / 图标 / i18n）质量高于同类项目。问题集中在四处，优先级差别很大：

| 层 | 现状 | 是否值得做 |
|---|---|---|
| **L1 结构** | 缺错误边界、状态不可寻址、Settings 切换丢草稿、转写搜索无空态 | **必做** —— 造成白屏与真实数据丢失 |
| **L2 布局层级** | 图标栏标签溢出、阅读无行宽上限、平板导航顺序反了 | 必做 |
| **L3 可访问性** | Field 不绑定错误、Tabs 非完整 ARIA、Dialog/Drawer 无焦点陷阱、5 组对比度不达标、小图标命中区 <44px（hover 门控非缺陷，见 §3 A7） | 必做（硬线） |
| **L4 装饰** | 克制：1 处 `animate-spin` 绕过 token、Chip hover 反向、disabled 不一致、死代码 | 最后做，只清债不加戏 |

现在界面“不够精致”的主因不是缺动效或渐变，而是：刷新丢当前任务、切设置分区丢草稿、键盘 Tab 跑出对话框、12px 徽标在暖底上读不清。

## 1. 判据（每条问题标适用规则）

- **R1 响应与延迟**：反馈在 pointer-down；UI 动效 ≤300ms；禁用 ease-in。
- **R2 动效该不该存在**：按出现频率决定；每次动效要能回答“为什么动”。
- **R3 位移与物理**：只动 transform/opacity；入场不从 scale(0)；popover 从触发源缩放；hover 位移须 `@media (hover:hover) and (pointer:fine)` 门控；同层图标风格统一、不用 emoji。
- **R4 材质与层级**：层级靠材质重量；滚动边缘用渐隐；字距/行高随字号变化；长文有可读行宽上限；尺寸用 rem/em 随用户字号放大。
- **R5 可达性硬线**：正文 ≥4.5:1、大字/非文本 UI ≥3:1；焦点可见不被遮挡；表单错误内联并绑定字段；ARIA 模式完整；触控目标 ≥44px。
- **R6 交互质感**：禁用 `transition: all`；退场快于入场；高频元素用 transition 而非 keyframes；stagger 30–80ms；拖拽有指针捕获与速度交接。
- **R7 结构与功能完整性**：界面回答“我在哪/能去哪/有什么/怎么退出”；相似东西行为一致；危险操作才确认；反馈分四类（状态/完成/警告/错误）。

## 2. 已验证基线（可复核，勿改坏）

- `src/ember/motion.css` 全篇只动 transform/opacity，ease-out `cubic-bezier(0.23,1,0.32,1)`，140–300ms，完整 `prefers-reduced-motion: reduce`（`motion.css:157-185`）—— 符合 R1/R3/R6。
- `src/ember/tokens.css:17-42` 类型阶每级带 `--line-height` 与 `--letter-spacing`，display/headline/section 用 -0.02em —— 符合 R4。
- `src/ember/ui/Button.tsx` / `Chip.tsx` / `Switch.tsx` / `Checkbox.tsx` 带 `.ember-press`（`motion.css:23-32`，`:active` scale 0.975）—— 符合 R1。
- `src/ember/ui/BilibiliMark.tsx:13-21` 内联 SVG 并区分 `role="img"` / `role="presentation"`；全仓无 emoji 充当图标 —— 符合 R3。
- `src/ember/ui/Spinner.tsx:11` `role="status"`；`Skeleton.tsx:5` `aria-hidden` —— 符合 R5。
- i18n：`node scripts/i18n-contract.cjs` 报告 507 keys、zh-CN/en-US 对齐（上一轮实测，本轮未重跑，见 §7）。

**硬性不达标数值（本机脚本复算，本轮已跑）**

| 前景 / 背景 | 对比度 | 判定 |
|---|---|---|
| `--color-line #d6d3d1` / `--color-canvas #fafaf9` | **1.43** | FAIL（非文本 UI 需 ≥3） |
| `--color-line` / `--color-surface #f5f5f4` | **1.37** | FAIL |
| `--color-warn #d97706` / `--color-surface` | **2.92** | FAIL（12px 文字需 ≥4.5） |
| `--color-ok #16a34a` / `--color-surface` | **3.02** | FAIL |
| `--color-danger #dc2626` / `--color-surface` | **4.43** | 临界失败 |
| `--color-ink-mute #78716c` / `--color-surface` | **4.40** | 临界失败 |
| `--color-ink-mute` / `--color-raised #e7e5e4` | **3.82** | FAIL |

达标参照：`ink/canvas` 16.74、`soft/surface` 6.99、`ember/canvas` 4.96、`mute/canvas` 4.59。

## 3. 分层级问题清单

### L1 · 结构（最高优先：白屏或数据丢失）

| # | 符号（文件:行） | 问题 | 依据 | 建议改法 |
|---|---|---|---|---|
| S1 | `src/ember/EmberApp.tsx:52-77` | **全仓无错误边界**：`grep -rn 'ErrorBoundary\|componentDidCatch' src` 为空。渲染期异常直接把整页变白屏。 | R7 不能困住用户 | `Router` 外加 ErrorBoundary，fallback 复用 `StartupScreen` 失败卡，提供重试/复制日志 |
| S2 | `src/ember/EmberApp.tsx` 全仓无 `useSearchParams`/`useParams`（`grep` 为空）+ `src/store/taskStore/index.ts` 的 `currentTaskId` | **状态不可寻址**：当前任务只存内存，刷新即丢，无法分享链接。 | R7 我在哪 | 选中任务进 URL（`/?task=<id>` 或 `/note/:id`），store 派生（须同时验证 Tauri HashRouter，`EmberApp.tsx:46-47`） |
| S3 | `src/ember/pages/settings/SettingsPage.tsx:77-89` | **切换设置分区静默丢弃草稿**：`Routes` 只渲染当前 section，未保存的局部 draft 随卸载消失。 | R7 相似行为一致 | 有 draft 时离开确认，或把 draft 提升到 SettingsPage |
| S4 | `src/ember/features/reader/TranscriptView.tsx:49-56` | 搜索无结果渲染**空列表容器**，无提示。 | R7 状态反馈 | `visible.length===0` 时给内联空态（复用 EmptyState 紧凑变体） |
| S5 | `src/ember/features/workspace/TaskCard.tsx:91` | `<Progress value={...} />` **不传 label** → `aria-label={undefined}`，屏幕阅读器读到无名进度条。（注：`TaskProgressCard.tsx:71` 有 label，不受影响） | R5 | `Progress` 无 label 时给默认名，或 `aria-label` 必填 |

### L2 · 布局层级

| # | 符号（文件:行） | 问题 | 依据 | 建议改法 |
|---|---|---|---|---|
| L2-1 | `src/ember/shell/AppShell.tsx:55` | `<span className="truncate xl:inline">` —— span 本就是 inline，`xl:inline` 在 <1280px **不会隐藏**标签；而 768–1279px 侧栏只有 76px（`AppShell.tsx:64` `md:w-[76px] xl:w-[256px]`），文字被截断挤在图标栏。 | R4 层级 / R7 | 改 `hidden xl:inline`（或 `sr-only` 保留可访问名） |
| L2-2 | `src/ember/features/reader/NotePanel.tsx:105-107`、`MarkdownNote.tsx` | 阅读区**无行宽上限**（`grep max-w` 仅图片 `max-w-full`），长段落拉成极宽一行。 | R4 可读行宽 | 正文列加 `max-w-[68ch]`；表格/代码可溢出 |
| L2-3 | `src/ember/pages/WorkspacePage.tsx:82-105`（`rail=` 传给 AppShell）+ `AppShell.tsx:98-104` | `lg` 以下 rail 折到内容下方，“历史任务列表”排在正文之后，与“compose 左/read 中/history 右”注释不符，历史是高频导航。 | R7 就近分组 | 平板下历史折到上方或做抽屉 |
| L2-4 | `src/ember/features/reader/NotePanel.tsx:97` | 大纲缩进用内联 px（`(depth-2)*10+12`），不随用户字号放大。 | R4 Dynamic Type | 换 `paddingInlineStart: calc(...)` 或 rem |
| L2-5 | `src/ember/ui/Card.tsx:26-27` | `selected` 用 `border-l-2` 覆盖默认 1px `border` → 左边界 1px→2px，**内容横跳 1px**。 | R3 状态不得改布局边界 | `ring-1 ring-inset`，或恒 2px 只换色 |
| L2-6 | `src/ember/pages/OnboardingPage.tsx:207-214` | 步骤条 `index <= step` 判填充 → 当前步与已完成步同色，只靠 ✓ 区分。 | R7 状态清晰 | 当前步用描边/环，已完成步才实心 |

### L3 · 可访问性（硬线）

| # | 符号（文件:行） | 问题 | 依据 | 建议改法 |
|---|---|---|---|---|
| A1 | `src/ember/ui/Field.tsx:22-27` | 错误/提示裸 `<p>`，**无 id、无 `aria-describedby`/`aria-invalid` 绑定控件**，读屏不会读错误。 | R5 错误绑定字段 | Field 用 `useId` 生成 id，经 context 传 Input/Textarea/Select，并置 `aria-invalid` |
| A2 | `src/ember/ui/Tabs.tsx:17-37` | 有 `role="tablist"/"tab"`、`aria-selected`，但**无 `role="tabpanel"`、无 `aria-controls`、无方向键/roving tabindex**，所有 tab 都在 Tab 序列里。 | R5 ARIA 完整 | 补 tabpanel + `aria-controls/labelledby`，实现左右漫游与 roving tabindex |
| A3 | `src/ember/ui/Dialog.tsx:30-43` | 有 Escape 与滚动锁，**无焦点陷阱**（`panelRef.current?.focus()` 后 Tab 会跑到背景），**关闭后不还原焦点**。 | R5 焦点可达 | 加焦点陷阱 + 关闭后 focus restore |
| A4 | `src/ember/ui/Drawer.tsx:23-30` | 只有 Escape；**无初始焦点、无陷阱、无滚动锁、无焦点恢复**。 | R5 | 与 Dialog 共用 overlay 焦点逻辑 |
| A5 | `src/ember/ui/Progress.tsx:31` | `aria-label={label}`，label 可空（见 S5）。 | R5 | 同上 |
| A6 | `src/ember/ui/Badge.tsx:11-17` + §2 表 | `warning` 2.92、`success` 3.02、`danger` 4.43 的 12px 文字在暖底上不达 4.5；`--color-line` 非文本 UI 仅 1.4。 | R5 硬线 | 加深前景（warn→#b45309、ok→#15803d），分隔线单列评估 |
| A7 | 手写过渡时长分散：`duration-150` **13 处**、`transition-colors` **12 处**（`grep -rho 'duration-[0-9]*' --include=*.tsx src/ember`），与 `motion.css` 的 `--dur-hover` 160ms / `--dur-press` 140ms 不一致；部分手写图标按钮没有 `.ember-press`。 | 同一次交互里不同控件收尾速度不同，观感不齐。 | R6 一致性 | 把 13 处 `duration-150` 统一到 `--dur-hover`(160ms)，按下态用 `--dur-press`(140ms)；手写图标按钮补 `.ember-press` |
| A8 | `src/ember/features/workspace/GroupPanel.tsx:228,239` 等 `p-1` + `size-3` | 命中区约 20×20px（4+12），低于 44px。 | R5 | 命中区扩到 44px，视觉可不变 |

### L4 · 装饰（最后做，只清债）

| # | 符号（文件:行） | 问题 | 依据 | 建议改法 |
|---|---|---|---|---|
| D1 | `src/ember/features/workspace/TaskProgressCard.tsx:51` | Tailwind `animate-spin`(1s) 绕过 `.ember-spin`(900ms，`motion.css:130`)，全仓仅此一处。 | R6 一致性 | 换 `.ember-spin` |
| D2 | `src/ember/ui/Chip.tsx:26` | 非激活 chip `bg-raised hover:bg-surface` —— hover 让底色**变亮**（#e7e5e4→#f5f5f4），与“hover 增强”相反。 | R3/R6 | hover 加深（`hover:bg-line`） |
| D3 | `src/ember/ui/Input.tsx:7`、`Select.tsx:25` | 用 `focus:` 而非 `focus-visible:` —— 鼠标点击也亮焦点环。 | R5 精神 | 关键控件改 `focus-visible`（`tokens.css` 全局 `:focus-visible` 兜底） |
| D4 | `src/ember/ui/Button.tsx` `disabled:opacity-50` vs `Input.tsx:8` `disabled:opacity-60` | disabled 弱化程度不一致。 | R7 一致性 | 统一 token（如 `--disabled-opacity`） |
| D5 | `src/ember/tokens.css:1` | 三个 Google 字体用 CSS `@import`（渲染阻塞），`index.html` 无 preconnect。 | R1 感知性能 | 改 `<link rel="preconnect">` + `display=swap` 的 `<link>`，或自托管子集 |
| D6 | `src/ember/ui/Tooltip.tsx` | **全仓零调用**（`grep Tooltip` 除自身外为空）—— 死代码；部分纯图标控件（`TaskList.tsx` 清除搜索、`ProviderModels.tsx` 删除）当前靠 `aria-label` 承担语义。 | R2/R7 | **删除原语**；受影响的纯图标按钮补 `aria-label`（不引入 tooltip 依赖） |
| D7 | `src/ember/features/reader/MarkdownNote.tsx:212` | `className="ember-markdown"` 但 CSS 无任何 `.ember-markdown` 规则。**不能删**：`scripts/ember-outline-probe.cjs:21`、`scripts/ember-reader-probe.cjs:43`、`scripts/probe-images2.cjs:16,20` 依赖该钩子。 | R7 一致性 | **保留 class 并补真实 CSS 规则**（排版/间距/图片圆角），使钩子名副其实 |

**L4 附注（记录，不在本轮做）**：全仓无 spring、无手势阻尼、HTML5 拖拽无速度交接（`TaskList.tsx:193-201`、`GroupPanel.tsx:88-96`）—— 属 R6 手感最后一档，后续专项。
## 4. 功能完整性缺口（已有的职责没做完，非新需求）

> 与视觉改进分开：这些是“能力已存在但缺入口/缺反馈”，需产品裁决，不混进 UI 改动。

| # | 现状证据 | 缺口 | 处置 |
|---|---|---|---|
| F1 | `src/services/note.ts:77,97` 导出 `downloadNoteArchive`/`downloadNoteArchives`，`grep` 在 `*.tsx` **无任何 UI 调用** | 归档导出已实现且无入口 | **已定：补 UI 入口**，接进笔记操作区 → 归 **W3** |
| F2 | `src/services/proxy.ts:11,18` 完整（后端 `backend/app/routers/config.py:322,334` 有 `/proxy_config`），`grep -i proxy` 在 `ember/` 只命中一条注释 | 代理设置无界面 | **已定：补设置界面**，W4 新增分区，需同步 i18n key → 归 **W4** |
| F3 | `src/services/upload.ts:4` `uploadFile`（后端 `backend/app/routers/note.py:1592` `/upload`），0 个 UI 调用者 | 同上 | 需人确认 |
| F4 | `src/ember/pages/settings/sections/ProviderModels.tsx:106-113` `test()` 无 busy 态 | 连点重复打上游（30–50s），无“正在测”反馈 | 加 loading（**属 L1 结构**，并入 W1） |
| F5 | 已声明但 0 引用的前端库（antd / @ant-design/x / @lobehub/icons / sonner / fuse.js / pinyin-match / jszip / markmap-view / react-resizable-panels / next-themes / lottie / markdown-navbar） | 产物体积 | **已定：单独开卡清理，不进 T-057 工作包** |
| F6 | `src/ember/tokens.css:92` `color-scheme: light`，全仓无 `prefers-color-scheme`/`dark:`；`ember-studio-DESIGN.md` 却写“light and dark 都要成立” | 文档与实现不一致 | **已定：维持浅色**，改 `ember-studio-DESIGN.md` 与 `color-scheme: light` 一致 → 归 **W0** |
| F7 | 无 ErrorBoundary（见 S1） | 见 S1 | 已列入 L1 / W2 |

## 5. 数据安全追加项（W4，优先于 S3）

设置分区审计发现的**会破坏用户数据**的问题，优先级高于“切换丢草稿”：

| # | 符号（文件:行） | 问题 | 依据 | 建议改法 |
|---|---|---|---|---|
| R-1 | `src/ember/pages/settings/sections/DownloadSection.tsx:26-27`（`.catch(() => undefined)`）+ `:38` `updateDownloaderCookie({ cookie, platform: 'bilibili' })` | cookie **读取失败被吞**，`cookie` 保持初始 `''`；用户随后点保存 → 用**空串覆盖**已存 cookie，登录态直接丢失。 | R7 不丢数据 | 读取失败置错误态并禁用保存；空串不得写入（`cookie.trim()` 非空才提交，或显式“清除”按钮 + 二次确认） |
| R-2 | `src/ember/pages/settings/sections/GeneralSection.tsx:61` `const { data, loading, reload } = useAsync(...)`（`error` 未取）+ `:64` `num = key => draft[key] ?? data?.[key] ?? 0` | `useAsync` 的 error 未呈现，数值字段回退 **0**；用户看到 0、改任意一项后保存，会把 26 个数值字段中的相关项写成 0（如并发生成数、缓存上限）。 | R7 反馈错误 + 不丢数据 | 取 error 并渲染错误态；`data` 未加载成功时禁用保存（`disabled={!data}`），数值回退仅用于显示占位而非可提交值 |
| R-3 | `src/ember/pages/settings/sections/MediaSection.tsx:61`（`previewMediaCleanup(RESOURCE_TYPES, true)`）vs `:141`（`clean(false)`） | “预览”恒定按 **仅过期** 口径，但“全部清理”按钮按 `expiredOnly=false` 执行 → 预览数字与实际删除量**不一致**，用户按预览预估点了全量删除。 | R7 相似行为一致 | 预览跟随即将执行的口径（两个按钮各自预览），或全量删除前弹确认并显示实际计数 |
| R-4 | `src/ember/pages/settings/sections/PromptSection.tsx:55-58` `restore = () => setDraft('')` | “恢复默认”**无确认**，一次点击清空整个提示词；虽未落库（仍需保存），但用户已丢失编辑内容且无撤销。 | R7 危险操作确认 | 加确认对话框；或提供“撤销”toast |
| R-5 | `src/ember/pages/settings/Section.tsx:36-45` `SettingRow` | 标签是 `<span>`，control 在相邻 `div` 里 —— Switch/Checkbox 等无 `aria-label` 时**没有可访问名**。 | R5 可达性 | `SettingRow` 用 `useId` + `aria-labelledby` 关联 label 与 control，或要求 control 自带 `aria-label` |
## 6. 工作包划分（W0–W5，逐文件写死）

> scope 只写文件，不写目录 —— 写目录会被判范围重叠而退化成串行。W5 显式依赖 W0–W4。

| 包 | 范围（逐文件） | 内容 | 依赖 |
|---|---|---|---|
| **W0** | `BillNote_frontend/src/ember/tokens.css`、`BillNote_frontend/src/ember/ui/Badge.tsx`、`BillNote_frontend/src/ember/ui/Chip.tsx`、`BillNote_frontend/index.html`、`ember-studio-DESIGN.md`（仓库根） | A6 对比度（**只调 line/warn/ok/danger/ink-mute，ember 与 ink 不动**；line 取刚好 ≥3:1）、D2 Chip hover 反向、D5 字体加载（`index.html` 加 preconnect crossorigin + 把 `tokens.css:1` 的 `@import` 换成 `<link>`）、**F6 维持浅色**：把 `ember-studio-DESIGN.md` 改成与 `tokens.css:92` 的 `color-scheme: light` 一致（删掉“light and dark 都要成立”的表述） | 无 |
| **W1** | `.../src/ember/ui/Field.tsx`、`Input.tsx`、`Textarea.tsx`、`Select.tsx`、`Tabs.tsx`、`Dialog.tsx`、`Drawer.tsx`、`Progress.tsx`、`.../src/ember/features/workspace/TaskCard.tsx` | A1 Field 错误绑定（useId + aria-describedby/aria-invalid）、A2 Tabs 完整 ARIA（tabpanel/aria-controls/方向键/roving tabindex）、A3+A4 overlay 焦点（陷阱 + 关闭还原，Dialog/Drawer 共用）、S5/A5 Progress 命名、D3 focus-visible、D4 disabled 统一、F4 连接测试 loading 的前置（origin 在 W4） | 无 |
| **W2** | `.../src/ember/EmberApp.tsx`、`.../src/ember/shell/AppShell.tsx`、`.../src/ember/shell/ErrorBoundary.tsx`（新建）、`.../src/ember/ui/Card.tsx`、`.../src/ember/pages/WorkspacePage.tsx`、`.../src/ember/pages/OnboardingPage.tsx` | S1 ErrorBoundary（fallback 复用 StartupScreen 失败卡）、L2-1 `hidden xl:inline`、L2-5 Card 选中边界不跳、L2-3 平板导航顺序、L2-6 步骤条状态。**W2 不碰路由**（S2 已拆出） | 无 |
| **W3** | `.../src/ember/features/reader/TranscriptView.tsx`、`NotePanel.tsx`、`MarkdownNote.tsx`、`.../src/services/note.ts` | S4 转写搜索空态、L2-2 阅读行宽上限、L2-4 大纲 rem、D7 **保留 `.ember-markdown` 并补真实 CSS**；**F1 归档导出接 UI 入口**（`note.ts:77,97` 的 `downloadNoteArchive`/`downloadNoteArchives` 接进笔记操作区，含 loading 与失败提示） | 无 |
| **W4** | `.../src/ember/pages/settings/SettingsPage.tsx`、`Section.tsx`、`sections/AboutSection.tsx`、`DownloadSection.tsx`、`GeneralSection.tsx`、`GlobalModelPicker.tsx`、`MediaSection.tsx`、`ModelSection.tsx`、`MonitorSection.tsx`、`OcrSection.tsx`、`PromptSection.tsx`、`ProviderDialog.tsx`、`ProviderModels.tsx`、`TranscriberSection.tsx`、`sections/ProxySection.tsx`（新建）、`.../src/services/proxy.ts`、`.../src/ember/i18n/strings.ts` | **先修 R-1…R-5 数据安全**（§5）；再做 S3 草稿跨分区保留（draft 提升到 SettingsPage + 修改角标）、F4 连接测试 loading、**F2 新增代理设置分区**（接 `services/proxy.ts:11,18` 与后端 `config.py:322,334` 的 `/proxy_config`，同步 i18n key） | 无 |
| **W5** | `.../src/ember/**/*.tsx` | **A7（一致性项）**：13 处 `duration-150` 统一到 `--dur-hover`(160ms)、按下态用 `--dur-press`(140ms)、12 处 `transition-colors` 对齐、手写图标按钮补 `.ember-press`；A8 命中区 ≥44px；D1 `animate-spin`→`.ember-spin`；D6 删除 `ui/Tooltip.tsx` 并给受影响纯图标按钮补 `aria-label` | **dependsOn W0–W4**（Chip/Input/Select/Progress/MarkdownNote 会被再碰） |

**已拆出本轮**：S2 URL 状态（状态可寻址）—— Q3 裁决不进本轮，单开卡，验收写「BrowserRouter 与 Tauri HashRouter 各验一次深链」，W2 不碰路由。

**已裁决归属**：F1 补 UI 入口 → W3；F2 补设置界面 → W4（新分区）；F6 维持浅色、改设计文档 → W0。

**不进 T-057**：F5 13 个 0 引用依赖 —— 人已定单独开卡清理，由调度另建。

**待确认**：F3 上传入口（`services/upload.ts:4`）人未作答，保持未排期。

## 7. 验证方式（可复现）

- **回归（每个工作包必须真跑并记 exit code）**：`cd BillNote_frontend && pnpm exec vitest run`、`pnpm exec tsc -b`、`pnpm lint`、`node scripts/i18n-contract.cjs`。
- **对比度（W0）**：`docs/ui-audit/evidence/contrast-ratios.txt` 的脚本复算；warn/ok/danger 在各自底色 ≥4.5（12px 文字），`--color-line` 作非文本 UI ≥3。W0 单独验收，前后截图各一份。
- **过渡一致性（W5，原 A7）**：判据不是“归零”而是“白名单内一致”——改后 `grep -rho 'duration-[0-9]*' --include=*.tsx src/ember` 只应出现 token 派生的时长，`duration-150` 从 13 处降到 0（改用 `--dur-hover` 160ms / `--dur-press` 140ms）；`transition-colors` 12 处逐条确认时长来源。前后输出存档到 `docs/ui-audit/evidence/`。
- **可访问性（W1）**：键盘全程无鼠标走一遍 —— Tab 顺序、Escape、焦点陷阱、关闭后焦点还原、错误是否被 `aria-describedby` 关联。
- **响应式（W2）**：375 / 768 / 1024 / 1440 四个宽度各截一次导航与阅读区。
- **不能假装验证的**：不以“看起来好了”代替上述命令与截图。

## 8. 风险与回滚

- **W0 改颜色变量影响全站观感** → 单独卡、单独验收；回滚 = 还原 `tokens.css` 颜色变量与 `index.html`。
- **W4 动设置保存路径** → 每条 R-1…R-4 都要有“读取失败仍不覆盖旧值”的验证；回滚 = 还原对应 section。
- **W5 依赖 W0–W4**，乱序会把 hover/命中区改到已被改写的控件上 → 必须等前四包合并后再派。
- 全程不改提示词语义、不改后端接口、不改 i18n key 语义、不改包管理与产物配置。

## 9. 本轮实际执行与未执行（如实）

- **已执行**：对比度脚本复算（数值见 §2）；`grep` 计数（`duration-150` 13 处、`transition-colors` 12 处、hover 47/52/27 三种口径，证据见 `docs/ui-audit/evidence/`）；S1–S5、L2-1…L2-6、A1–A8、D1–D7、R-1…R-5 的源码逐条核对（file:line 均为本轮实读）。
- **A7 已撤销**：原判定“47 处 hover 未门控”不成立。Tailwind v4（`package.json` `"tailwindcss": "^4.1.3"`）的 `hover:` 变体本身编译进 `@media (hover: hover)`，47/27/52 只是计数口径差异。本 worktree 无 `node_modules`，无法本地复核该编译行为，判据由调度在 `tailwindcss/dist/lib.js` 上确认；因此 A7 改为**一致性项**（见 §3）。
- **未执行**：`pnpm exec vitest/tsc/lint/build` 与 i18n 脚本 —— T-057 worktree 无 `node_modules`（`ls node_modules` → NO_NM），无法运行；这些命令在 W0–W5 实施卡里必须真跑。
- **未执行**：任何产品代码改动（本卡纪律：只出计划）。

## 10. 修订记录

- rev 6（2026-11-10）：落人的 4 项决定 —— F1 补归档导出入口（归 W3，含 `services/note.ts`）、F2 补代理设置分区（归 W4，新增 `sections/ProxySection.tsx` + `services/proxy.ts` + i18n）、F5 13 个 0 引用依赖单独开卡不进 T-057、F6 维持浅色并把 `ember-studio-DESIGN.md` 归 W0 改写。**撤销 A7 缺陷判定**（Tailwind v4 `hover:` 自带 `@media (hover: hover)` 门控），改为手写时长一致性项（`duration-150` 13 处 → `--dur-hover` 160ms / `--dur-press` 140ms、手写图标按钮补 `.ember-press`）。同步更新 §0 表与 W5 判据。
- rev 3（2026-11-10）：采纳 Q1–Q8 裁决 —— 按 W0–W5 逐文件收敛 scope 与依赖；S2 拆出本轮；hover 判据改为调度复现的 47 并记录差异；A6 限定 line/warn/ok/danger/ink-mute 且 ember/ink 不动；D6 改为删除 Tooltip + 补 aria-label；D7 改为保留 `.ember-markdown` 并补真实 CSS（probe 脚本依赖）；新增 §5 W4 数据安全五项；证据入库 `docs/ui-audit/`。
- rev 2：首版分层审计（S/L2/A/D 共 26 条 + 功能缺口 7 条）。
