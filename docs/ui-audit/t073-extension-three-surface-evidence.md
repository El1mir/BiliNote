# T-073 扩展三面重绘 — 证据

三个界面（Popup / Options / Sidepanel）按 `specs/021-*` token 重绘：深石墨 + 冷白 + 青绿，浅色默认、深色跟随 `prefers-color-scheme`。本文件记录实测数据与截图索引。

## 1. 真尺寸（Playwright 1.61.1 / chromium-1248，静态服务 root = `BillNote_extension/extension`）

| 面 | viewport | overflowX | scrollHeight / clientHeight | <44px 可点目标 |
|---|---|---|---|---|
| Popup | 400x600 | 0 | 600 / 600 | 0 |
| Sidepanel | 360x800 | 0 | 800 / 800 | 0 |
| Options | 1280x800 | 0 | 800 / 800 | 0（`hasTouch` 下） |

桌面态 Options 的「测试连通」「刷新」高 34px；`@media (pointer: coarse)` 下抬到 44px，故触控测量为 0 个小目标。

## 2. 颜色（getComputedStyle）

| 主题 | 页面底色 | 正文墨色 |
|---|---|---|
| 浅色 | `rgb(244, 246, 247)` | `rgb(23, 33, 38)` |
| 深色 | `rgb(17, 23, 25)` | `rgb(237, 244, 243)` |

状态胶囊：浅色 `status-running` bg `rgb(232,243,241)` / fg `rgb(7,117,111)`，失败 bg `rgb(253,236,234)` / fg `rgb(180,35,24)`；深色对应 `rgb(20,49,47)` / `rgb(67,199,182)`、`rgb(58,27,24)` / `rgb(255,140,131)`。
阶段条（TRANSCRIBING）：前 4 段 `rgb(7,117,111)`，后 4 段 `rgb(240,244,245)`（深色 `rgb(38,51,54)`）。

旧 terracotta `#c2410c` 在 `BillNote_extension/src` 已无残留。

## 3. 键盘

提交按钮 focus 后按 Enter → fetch 依次命中 `/api/sys_check` → `api.bilibili.com/x/web-interface/view` → `/api/generate_note`，`generateCalled=true`（按钮 enabled 时）。表单为 `<form @submit.prevent>` + `<button type="submit">`，未用 div 模拟按钮。

## 4. 四态

| 状态 | Popup | Sidepanel | 说明 |
|---|---|---|---|
| 加载 | `.spin` + 正在连接后端… | 同 | `booting`/`checking` |
| 空 | 还没有任务… | 还没有任务… | |
| 失败 | `.banner-danger role=alert` + 任务级 `status-failed` | 同（含 `backend error: model_not_found 200105`） | |
| 后端不可用 | `.banner-danger` 后端不可用（detail）+ 去设置 | 同 | `useBackendHealth` 4s 超时 |

## 5. 截图索引（`docs/ui-audit/evidence/t073/`）

- `popup-{light,dark}-400x600.png`、`popup-loading-400x600.png`、`popup-empty-backend-down-400x600.png`、`popup-history-failed-400x600.png`
- `sidepanel-{light,dark}-360x800.png`、`sidepanel-failed-360x800.png`、`sidepanel-empty-backend-down-360x800.png`
- `options-{light,dark,touch}-1280x800.png`、`options-{general,providers,transcriber,downloader,monitor}-{light,dark}-1280x800.png`

## 6. 门禁

```
pnpm build        exit 0
pnpm typecheck    exit 0
CI=1 pnpm exec vitest run → 3 files / 5 tests passed
```

`pnpm test:e2e` 未跑：需要 Playwright 浏览器。补跑：`pnpm exec playwright install chromium && pnpm test:e2e`。

## 7. 复现

1. `cd BillNote_extension && pnpm build`
2. 用任意静态服务器以 `BillNote_extension/extension` 为 root 起服务（构建产物在 `extension/dist`，HTML 用绝对路径 `/dist/assets/*`）
3. Playwright 注入 `window.chrome` 桩（`runtime/tabs/storage`）与 `bilinote-settings`/`bilinote-tasks` 两个 storage 键，再打开 `/dist/{popup,sidepanel,options}/index.html`

桩的要点：webextension-polyfill 要求 `chrome.runtime.id`；storage 值必须是 JSON 字符串；task_status 桩要返回 `{status:'TRANSCRIBING'}` 否则 Popup 的 3s 轮询会把状态清空。
