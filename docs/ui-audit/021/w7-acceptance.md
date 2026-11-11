# 021 · W7 集成验收：8 条验收逐条证据

日期：2026-11-11 · 卡：T-075 · 分支 flow/T-066 · 基线 f657ab2

本文件只记录**真实跑过**的证据；没跑的写 BLOCKED / 红，不写通过。

## 运行环境（截图口径）

- 前端：`cd BillNote_frontend && pnpm dev` → http://127.0.0.1:3015
- 后端：`python .t075-run/mock.py`（临时脚本，未入库）监听 127.0.0.1:8483，提供 `/api/sys_check`、`/api/sys_health`、`/api/task_list`、`/api/task_status/{id}`、`/api/task_status/batch`、`/api/v1/task-groups/snapshot`、`/api/v1/task-groups/events`（空 SSE）、`/api/note_group`、设置页读接口与 `/static/screenshots/probe.svg`。
- 截图：Playwright（`BillNote_extension/node_modules/playwright`，chromium-1181 可执行文件）真实视口 + `localStorage['bilinote-theme']` 预设浅/深。
- 扩展截图：`pnpm build` 后以 `launchPersistentContext(--load-extension=BillNote_extension/extension)` 加载，`context.route('http://localhost:8483/**')` mock 后端。

## 1. 页面全覆盖 + 功能回归

覆盖页面：工作区（单集/批量/分组/历史/任务卡/阅读区）、设置（通用/模型/转写/下载/部署监控）、引导（步骤流/启动屏）、扩展 popup/options/sidepanel、404。

| 证据 | 覆盖 |
|---|---|
| `docs/ui-audit/021/w7-1440-{light,dark}.png` | 工作区浅/深 |
| `docs/ui-audit/021/w7-reader-1440-{light,dark}.png` | 阅读区（笔记正文渲染、已完成任务卡、复制/下载/归档入口） |
| `docs/ui-audit/021/w7-settings-1440-{light,dark}.png` | 设置页浅/深 |
| `docs/ui-audit/021/w7-onboarding-1440-light.png` | 引导页 |
| `docs/ui-audit/021/w7-transcript-empty-1440-light.png` | 转写搜索无结果空态 |
| `docs/ui-audit/021/w7-ext-{popup,options}-{light,dark}-*.png`、`w7-ext-sidepanel-light-360x800.png` | 扩展三面 |
| `docs/ui-audit/evidence/t069..t073/`（14 / 10 / 15 / 21 / 31 个文件，含 metrics/README） | 各子卡的加载/失败/空态/拖拽/删除确认等 |

功能回归：前端 `pnpm exec vitest run` 30 files / 197 tests 全过；阅读区与工作区在浏览器里实测可渲染 mock 笔记（`w7-reader-1440-*` 截图内正文/大纲/标签页均在位）。**结论：pass**（后端真实生成链路未跑，见 #8 说明）。

## 2. 语义 token 双主题

- `BillNote_frontend/src/ember/tokens.css`：`:root` 浅色、`.dark` 深色，同一批语义名（canvas/surface/raised/ink/ink-soft/ink-muted/line/line-strong/accent/on-accent/success/warning/danger/info）。
- 实测画布：浅色 `rgb(244, 246, 247)`（#f4f6f7），深色 `rgb(17, 23, 25)`（#111719）——见 `w7-runtime-metrics.json`。
- `BillNote_frontend/tests/021-workbench-redesign/tokens.test.ts`（双主题同名校验、hex 扫描）与 `theme.test.ts`（三态解析）在 197 例中通过。
- 扩展 `BillNote_extension/src/styles/tokens.css` + `unocss.config.ts` 映射同一批 CSS 变量；`src/__tests__/tokens.test.ts` 5 例通过。

**结论：pass**

## 3. 375 / 768 / 1024 / 1440 响应式 + 扩展真实尺寸

| 宽度 | scrollWidth / clientWidth | 横向溢出 | 证据 |
|---|---|---|---|
| 375 | 365 / 365 | 否 | `w7-375-{light,dark}.png` |
| 768 | 758 / 758 | 否 | `w7-768-{light,dark}.png` |
| 1024 | 1024 / 1024 | 否 | `w7-1024-{light,dark}.png` |
| 1440 | 1440 / 1440 | 否 | `w7-1440-{light,dark}.png` |

（`w7-runtime-metrics.json`；768/375 的 10px 差来自窗口滚动条占位，与 W0 同口径。）

扩展：popup 400×600 → 400/400；options 1280×800 → 1280/1280；sidepanel 360×800 → 360/360（`w7-ext-*.png` + `w7-ext-metrics.json`；T-073 `docs/ui-audit/evidence/t073/README.md` 另有 8 组同尺寸实测）。

**结论：pass**

## 4. WCAG AA：对比度 / 键盘 / 44px 触控 / reduced-motion

- 对比度：`node docs/ui-audit/021/contrast-audit.mjs` → exit 0，13 对 × 2 主题全部 PASS（正文 ≥4.5:1，控件边框/焦点环 ≥3:1）。浅色最低 `line-strong on surface 3.40:1`、深色最低 `line-strong on surface 3.89:1`；输出在 `docs/ui-audit/021/contrast.txt`。
- 键盘：popup Tab 顺序与 Enter 提交见 `docs/ui-audit/evidence/t073/README.md`（设置 → 3 下拉 → 4 复选框 → 高级 → 生成笔记；Enter 出 taskId=t1/TRANSCRIBING）。Web 端 Dialog/Drawer 的 Escape、遮罩关闭、焦点回归由 `useOverlayFocus` 承担，T-070 浏览器探针 4 项全 true（`docs/ui-audit/evidence/t070/README.md`）。
- 44px 触控：`tokens.css` 的 `@media (pointer: coarse)` 覆盖 button / [role=button] / select / input / textarea / summary 为 `min-height: 2.75rem`；T-073 以 `--blink-settings=primaryPointerType=2,availablePointerTypes=2` 实测 12 个控件全部 ≥44px（summary 由 16 修到 44，见 `docs/ui-audit/evidence/t073/README.md`）。
- reduced-motion：`BillNote_frontend/src/ember/motion.css:8` 起的 `@media (prefers-reduced-motion: reduce)` 保留颜色/透明度、去掉位移（规则与注释在文件内）。

**结论：pass**

## 5. 空态 / 错误态 / 禁用态 / 保存态

- 工作区空态：`w7-1440-*` 中「还没有笔记 / 粘贴一个视频链接，开始生成你的第一条笔记」。
- 任务失败态、加载态、后端不可用态：`evidence/t069/`（failed/loading/backend-down）、`evidence/t073/`（popup loading/failed/backend-down）。
- 设置页保存态：`evidence/t071/settings-save-saved-1024-light.png`（保存后按钮/提示），另有 OCR 加载错误、测试忙碌、媒体清理确认等 14 张。
- 引导页步骤态：`evidence/t072/`（21 张，含启动屏、后端失败、步骤校验）。
- 阅读区空态：`tests/021-workbench-redesign/reader.test.tsx` 断言空态文案；转写无结果：`w7-transcript-empty-1440-light.png`（「没有匹配「不存在的词zzz」的转写 / 换个关键词试试，共 5 条转写内容。」）。

**结论：pass**（以上为各子卡在本分支历史提交上的截图；W7 未逐页重跑全部 91 个文件）

## 6. 集中动效 token 120–300ms

`BillNote_frontend/src/ember/motion.css:14-22`：

```
--dur-press: 120ms; --dur-hover: 160ms; --dur-popover: 180ms; --dur-menu: 200ms;
--dur-panel: 260ms; --dur-dialog/--dur-drawer: var(--dur-panel); --dur-page: 300ms; --dur-progress: 300ms;
```

`grep -rhoE 'duration-[0-9]+' --include=*.tsx BillNote_frontend/src/ember | wc -l` → 0（无硬编码时长残留，T-063 复验）。扩展 tokens.css 同一阶梯。

**结论：pass**

## 7. Tauri 零残留

命令与结果见 `docs/ui-audit/021/tauri-residue.txt`：

- `git grep -il tauri` 只剩 CHANGELOG / README 更新记录 / CLAUDE.md / backend/main.py:95 注释 / backend 测试历史报告 / docs 证据 / specs / wayfinder；`BillNote_frontend/src`、`package.json`、`pnpm-lock.yaml` 命中 0。
- `Test-Path src-tauri` / `BillNote_frontend/src-tauri` / `node_modules/@tauri-apps` 全 False。
- `HashRouter|__TAURI_INTERNALS__|isTauri` 在 `BillNote_frontend/src` 命中 0；路由只有 `BrowserRouter`（EmberApp.tsx:2,45）。

**结论：pass**

## 8. 门禁全绿 + 截图/对比度证据

| 门禁 | 结果 |
|---|---|
| 前端 `vitest run` | 0 · 30 files / 197 tests |
| 前端 `tsc -b` | 0 |
| 前端 `lint` | 0 |
| 前端 `i18n-contract` | 0 · 572 keys（zh-CN / en-US 对齐） |
| 前端 `build` | 0（收口轮复跑 14.96s） |
| 扩展 `typecheck` | 0（修 tsconfig types 后；首跑 exit 2，见 `gates.md`） |
| 扩展 `vitest run` | 0 · 4 files / 10 tests |
| 扩展 `build` | 0（收口轮复跑 1.48s） |
| 扩展 `test:e2e` | **1（红）** · 3 failed，原因是 `e2e/basic.spec.ts` 仍是 vitesse-webext 模板断言（「Open Options」按钮、`img alt="extension icon"`），UI 已在 spec 017 重写；另 chromium-1129 未安装、官方下载在本机无进展 |

命令级输出与对比度脚本原文都贴在 `docs/ui-audit/021/gates.md`（含收口轮复跑的 exit code 表）。

**结论：partial** —— 前端五条 + 扩展 typecheck/test/build 绿；`test:e2e` 红，已定位为陈旧模板用例而非产品回归，需单独修复卡（改写 `e2e/basic.spec.ts` 断言 popup「生成笔记」与 options「后端地址」）。

## 证据文件清单（本卡新增）

- `docs/ui-audit/021/w7-*.png`：4 档宽度 × 浅/深（8 张）、阅读区浅/深（2）、设置浅/深（2）、引导（1）、转写空态（1）、扩展 popup/options 浅深（4）、sidepanel（1）。
- `docs/ui-audit/021/w7-runtime-metrics.json`、`w7-ext-metrics.json`：实测宽度/画布色/字体。
- `docs/ui-audit/021/gates.md`：8 条门禁命令 + exit code + 摘要。
- `docs/ui-audit/021/tauri-residue.txt`：残留判据命令与输出。
- `docs/ui-audit/021/contrast.txt`：双主题对比度（脚本读取 tokens.css 原文）。