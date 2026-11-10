# W2 阅读区（T-070）运行态证据

探针：Playwright 驱动 chromium（headless=new）打开 vite dev（127.0.0.1:3015），
API 指向本地 mock 后端（127.0.0.1:8499，一个 SUCCESS 任务，笔记含标题/表格/引用/ts 代码块/截图，
转写 5 段）。mock 与探针脚本是一次性的，未入库；结论数字见 `w2-runtime-checks.json`。

## 尺寸与行长

| 视口 | 阅读列实测宽 | 页面横向溢出 | 证据 |
|---|---|---|---|
| 1440×900 | 506px（≈68ch 上限内，列本身 max-w-[68ch]） | 无 | `w2-reader-1440-light.png`、`w2-note-body-1440-light.png` |
| 1024×800 | 522px | 无（scrollWidth 1014 = clientWidth 1014） | `w2-reader-1024-light.png` |

`pre { overflow-x: auto }` 在代码块上生效；截图 `img { max-width: 100% }` 生效，图片按钮
`aria-label="查看大图：截图说明"`。

## 深色可读（验收 #2）

`html.dark` → body 背景 `rgb(17,23,25)`（`#111719`）。同一篇笔记里：

- 代码块关键字色 `rgb(198,120,221)`（oneDark 紫），不再是浅色主题的近黑；
- 引用块文字 `rgb(192,207,206)`（`--ink-soft`）；
- 表格单元格文字 `rgb(237,244,243)`（`--ink`）。

证据：`w2-note-body-1440-dark.png`。

## 灯箱（验收 #1）

图片点是 `button.ember-zoom-trigger`，打开 `Dialog`（`useOverlayFocus`）：

- 打开后焦点进入 dialog：true
- Escape 关闭：true
- 遮罩点击关闭：true
- 关闭后 `document.activeElement` 回到触发按钮：true

证据：`w2-lightbox-1440-dark.png`。

## 转写搜索（验收 #2）

- 输入 `react` → 计数「匹配 2 / 5 条转写」，只剩两行（`w2-transcript-search-1440.png`）。
- 输入 `不存在的词zzz` → 计数「匹配 0 / 5」，空态「没有匹配「不存在的词zzz」的转写 /
  换个关键词试试，共 5 条转写内容。」+「清除搜索」（`w2-transcript-empty-1440.png`）。

## 结构回归

`BillNote_frontend/tests/021-workbench-redesign/reader.test.tsx`（10 例）用
`renderToStaticMarkup` 钉住：68ch 列、sticky 大纲、表格 overflow-x-auto、图片触发按钮与
aria-label、复制/下载/归档入口、空 reader、reader.css 的衬线 16/28 与 `scroll-margin-top: 6rem`、
Prism 主题映射、转写过滤计数、大纲 id/深度。仓库没有 jsdom，Escape/焦点这类 DOM 行为由本目录的
浏览器证据承担。
