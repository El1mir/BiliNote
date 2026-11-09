# W2 应用外壳 — 实测记录（T-060）

隔离栈：backend 127.0.0.1:8494（临时 SQLite `.t060-tmp/db/bili_note.db`，ASR 重依赖打桩）
+ Vite 127.0.0.1:3022；浏览器 chromium-1248（Playwright，无头）。临时库/配置/服务已全部清理。

## 1. 错误边界（截图 `w2-error-boundary-1024.png` / `w2-error-boundary-recovered-1024.png`）

探针方式：临时在 `NotFoundPage` 顶部 `throw new Error('T-060 boundary probe')`，访问 `/nope`。
探针代码已 `git checkout` 还原，未进入提交。

| 观察点 | 结果 |
| --- | --- |
| 是否白屏 | 否；`[data-boundary-state="error"]` 卡片存在，页面仍有内容与 3 个图标 |
| 卡片标题 | 页面遇到问题（scope：router） |
| 错误串 | `Error: T-060 boundary probe`（`data-boundary-error`） |
| 按钮 | 重试、复制日志 |
| 复制日志 | 按钮变「已复制」，剪贴板内容以 `Error: T-060 boundary probe` 开头并含 `at NotFoundPage (...)` 栈 |
| 故障未排除时点「重试」 | 仍是失败卡（未白屏、未死循环） |
| 故障排除后点「重试」 | 恢复渲染 NotFound 页（「页面不存在 / 返回工作区」） |

## 2. 侧栏标签（截图 `w2-workspace-{375,768,1024,1440}.png`）

|`nav` 标签 | 375 | 768 | 1024 | 1440 |
| --- | --- | --- | --- | --- |
| aside 宽度 | 0（隐藏，走抽屉） | 76px | 76px | 256px |
| 「工作区」标签 | display:none, 0px | display:none, 0px | display:none, 0px | display:block, 48px |
| 「设置」标签 | display:none, 0px | display:none, 0px | display:none, 0px | display:block, 32px |

768–1023px 只出图标，无一像素被截断的文字；≥1280px 出现标签。

## 3. Card 选中态（截图 `w2-card-selected-1440.png`）

设置 → 转写器，两个 ASR 接口卡（真实 UI，切换激活项前后各测一次）：

| 实现 | 卡片 left | 卡片 width | 首个子元素相对卡片左边距 |
| --- | --- | --- | --- |
| 未选中 | 536 | 880 | 1px |
| 旧实现 `border-l-2 border-l-ember` | 536 | 880 | **2px**（+1px 位移） |
| 本次实现 `border-ember ring-1 ring-ember ring-inset` | 536 | 880 | 1px |

切换激活项（one ⇄ two）前后，两张卡的 left/width/子元素偏移完全一致，均为 1px。

## 4. lg 以下历史列表位置（同 §2 截图）

主区包裹元素的两个子项（正文 / 历史 rail）实测 top：

| 宽度 | 历史 rail top | 正文 top | 结论 |
| --- | --- | --- | --- |
| 375 | 81 | 746 | 历史在前 |
| 768 | 24 | 689 | 历史在前 |
| 1024 | 32 | 32 | 并排（正文左、历史右） |
| 1440 | 32 | 32 | 并排 |

实现方式：`AppShell` 给正文 `order-2 lg:order-1`、给 rail 包裹 `order-1 lg:order-2`，
DOM 顺序与 lg 断点数值均未改动，因此 1024 以上布局与改动前一致。

## 5. 步骤条（截图 `w2-onboarding-steps-1024.png` / `w2-onboarding-steps-step2-1024.png`）

第 1 步时：step1 = current（`bg rgb(250,250,249)`、`color rgb(194,65,12)`、`border 2px rgb(194,65,12)`），其余 upcoming（1px 灰边）。
推进到第 2 步后：step1 = done（`bg rgb(194,65,12)`、白色对勾），step2 = current（描边 + 橙色数字），step3/4 = upcoming。

## 6. 门禁

```
cd BillNote_frontend && pnpm exec vitest run  # 17 files / 100 tests passed
pnpm exec tsc -b                              # exit 0
pnpm lint                                     # exit 0
```
