# W2 · 应用外壳与阅读排版

日期：2026-11-10 · 依赖：cfee166（W1 token 地基）

## 改了什么

### Topbar（`src/ember/shell/Topbar.tsx`）
- 桌面 ≥768px 一条 48px 的粘性栏：`BiliNote / <当前页>` 面包屑 + 后端状态 + 主题 + 语言。
- 页面自己的 `h1` 保留：顶栏是定位层，不是第二个标题。
- 状态是**圆点 + 文字**（`role="status"`），不只靠颜色；三态 checking / online / offline。

### 后端存活探针（`src/ember/shell/useBackendStatus.ts`）
- 复用 `useCheckBackend` 的 `getBackendBase()`（改为导出），`/sys_check` 每 30s 探一次，5s 超时。
- 为什么不用启动门禁那个 hook：它是一次性闸门，跑完就不再更新；顶栏需要在会话中途反映后端被关掉。
- 刻意不做退避重试（`ponytail:` 注释）：一个存活指示灯不需要重试策略。

### 阅读排版（`src/ember/reader.css`）
- `.ember-markdown` 正文改衬线（Source Serif 4 / Noto Serif SC），标题同步。
- `:is(p, li, blockquote)` 提到 16px / 1.75 —— 无层规则压过 `text-body` 工具类，组件不用改。
- 行宽沿用已有 `max-w-[68ch]` 列。

### 触控目标（`src/ember/tokens.css`）
- `@media (pointer: coarse)` 下 `button` / `[role=button]` / `select` 最小 44×44px。
- 只对触摸指针生效，桌面密度不变；正文里的行内链接按 WCAG 2.5.8 豁免。

## 验证

| 命令 | 结果 |
|---|---|
| `pnpm exec vitest run` | exit 0 · 24 files / 151 tests |
| `pnpm exec tsc -b` | exit 0 |
| `pnpm lint` | exit 0 |
| `pnpm build` | exit 0 |

运行态：mock 后端（`.quarantine-run/mock-w2b.py`，未入库）+ `pnpm dev` 3015，Chromium 实测。

| 证据 | 内容 |
|---|---|
| `evidence/w2-topbar-light.png` | 1384px 浅色：面包屑、绿点「后端已连接」、主题/语言 |
| `evidence/w2-topbar-dark.png` | 同尺寸深色 |
| `evidence/w2-375.png` | 375 CSS px：移动顶栏 + 抽屉入口 |
| `evidence/w2-768.png` | 768 CSS px：图标栏 + 顶栏 |
| `evidence/w2-1024.png` | 1024 CSS px |
| `evidence/w2-1440.png` | 1440 CSS px（布局按 1440 计算，截图 0.92 缩放以入画） |

## 尚未做（后续工作包）
- Workspace 三栏重排；小屏把分组/历史收进 Drawer（现在 375/768 仍是分组在最上面，表单位于其下）。
- Reader 实体页衬线效果未在运行态核验：mock 没有构造出 succeeded + markdown 的任务。
- Settings 分区、Onboarding 步骤流、扩展 Popup/Options/Sidepanel。
- 键盘流程、Dialog/Drawer 焦点约束复验。