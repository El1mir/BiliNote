# BiliNote Workbench — Design System

状态：approved（W0 地基，2026-11-10）· 适用：Web 主应用 + 浏览器扩展

这是 Web 与扩展唯一视觉参照。任何页面出现与本文件不一致的颜色、字号、间距、动效，都是缺陷。

## 1. 颜色 token

语义名固定为 12 个；浅色默认（`:root`），深色在 `.dark`。组件只消费 Tailwind 语义工具类（`bg-canvas`、`text-ink`、`border-line-strong`…），不写 hex。

| token | 浅色 | 深色 | 用途 |
|---|---|---|---|
| `canvas` | `#f4f6f7` | `#111719` | 页面底色 |
| `surface` | `#ffffff` | `#182124` | 卡片、面板 |
| `raised` | `#fbfcfc` | `#202b2e` | 菜单、浮层、二级面 |
| `ink` | `#172126` | `#edf4f3` | 主文本 |
| `ink-soft` | `#526168` | `#c0cfce` | 次级文本 |
| `ink-muted` | `#5f6d74` | `#91a3a5` | 辅助文本 |
| `line` | `#cbd5d8` | `#3b4a4d` | 分隔线 |
| `line-strong` | `#7e8e94` | `#6b7f82` | 控件边框（非文本≥3:1） |
| `accent` | `#07756f` | `#43c7b6` | 主动作、当前项、焦点、进度 |
| `success` | `#18794e` | `#62c891` | 成功 |
| `warning` | `#926100` | `#f1c75b` | 警告 |
| `danger` | `#b42318` | `#ff8c83` | 错误、危险操作 |
| `info` | `#1769aa` | `#8dc7f0` | 信息 |

配套：`accent-hover` / `accent-soft` / `accent-ring` / `on-accent`、`success-soft` / `warning-soft` / `danger-soft` / `info-soft`、`on-danger`、`raised-hover`。

规则：
- 正文≥4.5:1、非文本 UI≥3:1，两套主题分别计算，脚本见 `docs/ui-audit/021/contrast-audit.mjs`。
- 状态必须有文字或图标，不得只靠颜色。
- 主色只用于交互与当前态，不整片铺底。

### 别名（W0 过渡）
`primary*` / `ink-mute` 是 `accent*` / `ink-muted` 的别名，供尚未迁移的 `pages/**`、`features/**` 使用。新代码一律用语义名；W1–W5 完成后删除别名。

## 2. 字体与字号

| 族 | 字体 | 用途 |
|---|---|---|
| `--font-sans` | Inter | 全部 UI 文本 |
| `--font-serif` | Source Serif 4 | Markdown 正文与标题 |
| `--font-mono` | IBM Plex Mono | ID、URL、模型名、代码、错误串 |

三者经 `@fontsource` 自托管（`src/fonts.ts`，latin 子集）；CJK 走系统栈。首屏不请求任何第三方域名。

字号：页面标题 28/34、区域标题 20/26、卡片标题 15/21、正文 14/22、辅助 13/19、状态 12/16。阅读列 ≤68ch，正文 16/28。

## 3. 间距、圆角、层级

- 间距基准 4/8px；容器内边距 16/24px。
- 圆角：`--radius-inline` 4px（行内）、`--radius-control` 8px（控件）、`--radius-surface` 12px（内容面）。
- 层级：细边界优先于阴影；`--shadow-raise` 只给浮起元素，`--shadow-float` 只给弹层。

## 4. 动效

`src/ember/motion.css` 定义唯一来源：

| token | 值 | 用途 |
|---|---|---|
| `--dur-press` | 120ms | 按下反馈 |
| `--dur-hover` | 160ms | 悬停、焦点 |
| `--dur-popover` | 180ms | 菜单、提示 |
| `--dur-menu` | 200ms | 下拉 |
| `--dur-panel` | 260ms | Dialog / Drawer（dialog、drawer 为别名） |
| `--dur-page` | 300ms | 页面级过渡 |

曲线：`--ease`（ease-out 主用）、`--ease-inout`、`--ease-drawer`。

规则：
- 只动 `transform` / `opacity`；按下 `scale(.975)`，不用 `scale(0)`。
- 每段动效必须可中断，不做持续装饰动画。
- `prefers-reduced-motion: reduce` 下关闭非必要动画与长距离位移。

## 5. 布局

- AppShell：≥1280px 256px 侧栏 + Topbar；768–1279px 72px 图标栏（图标链接必须带 `aria-label`）；<768px 顶部栏 + Drawer。
- Topbar：面包屑 + 后端存活状态 + 主题 + 语言，高 48px，粘性。
- 主题：三态 `light` / `dark` / `system`，`localStorage['bilinote-theme']`，`initTheme()` 在 React 挂载前写 `<html class="dark">` 与 `color-scheme`，刷新无闪白。

## 6. 校验

```bash
node docs/ui-audit/021/contrast-audit.mjs      # 双主题全部对比度
cd BillNote_frontend && pnpm exec vitest run tests/021-workbench-redesign
```

`tokens.test.ts` 读取 `tokens.css` 原文，断言 12 个语义名在两套主题都存在、对比度达标、`ui/` 与 `shell/` 无 hex 残留（BilibiliMark 品牌色除外）。