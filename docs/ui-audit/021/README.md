# 021 · W0 地基验收材料

## 对比度

`contrast-audit.mjs` 直接读取 `BillNote_frontend/src/ember/tokens.css`，因此数字不会与运行中的样式漂移。

```bash
node docs/ui-audit/021/contrast-audit.mjs
```

输出见 `contrast.txt`：浅色 13 对、深色 13 对，全部 PASS（正文 ≥4.5:1，非文本 ≥3:1）。

## 自动化

`BillNote_frontend/tests/021-workbench-redesign/`

| 文件 | 钉住什么 |
|---|---|
| `tokens.test.ts` | 12 个语义名在两套主题都存在且为合法 hex；对比度达标；`ui/` 与 `shell/` 无 hex（BilibiliMark 除外）、无 terracotta/Playfair 残留 |
| `theme.test.ts` | `resolveTheme` 六种组合、`nextTheme` 循环顺序 |

## 运行态

| 证据 | 内容 |
|---|---|
| `w0-theme-light.png` | 顶栏「主题: 浅色」，页面为浅色 |
| `w0-theme-dark.png` | 顶栏「主题: 深色」 |
| `w0-theme-system.png` | 顶栏「主题: 跟随系统」，OS 深色时页面为深色 |
| `w0-rail-768.png` | 768px 图标栏 |
| `w0-width-{375,768,1024,1440}.png` | 四档宽度 |
| `contrast.txt` | 双主题对比度表 |

实测（Chromium，1384px 宿主视口，iframe 真实媒体查询）：

| 宽度 | 文档 scrollWidth / clientWidth | 横向溢出 |
|---|---|---|
| 375 | 365 / 365 | 否 |
| 768 | 758 / 758 | 否 |
| 1024 | 1024 / 1024 | 否 |
| 1440 | 1440 / 1440 | 否 |

主题持久化：`localStorage['bilinote-theme']` 依次写入 light / dark / system，刷新后仍为 system 且首帧即深色（`initTheme()` 在 `createRoot` 之前执行）。

导航可访问名（iframe 内实测）：`a[aria-label]` = 工作区、设置；当前项 `aria-current="page"`。

字体请求：只有 `/node_modules/@fontsource/*/latin-*.css`，`fonts.googleapis.com` / `fonts.gstatic.com` 命中 0。

字体：`dist/assets/*.woff2` 由 @fontsource 产出；`index.html` 不再有 `fonts.googleapis.com`。