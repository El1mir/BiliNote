# T-072 · W4 引导 / 启动屏 / 404 / 错误边界 证据

面：首次引导（4 步）、启动等待与失败、404、错误边界回退。
驱动：Vite dev 3036（`VITE_API_BASE_URL=http://127.0.0.1:8486/api`）+ 临时 mock 后端 8486（只供本轮截图，不提交）；
Playwright chromium-1248。截图在 `docs/ui-audit/evidence/t072/`。

## 1. 四档布局与溢出

| 面 | 视口 | overflowX | scrollWidth/Width | scrollHeight/Height | 主题 |
| --- | --- | --- | --- | --- | --- |
| onboarding step1 | 1440x900 | 0 | 1440/1440 | 900/900 | light |
| onboarding step1 | 1024x900 | 0 | 1024/1024 | 900/900 | light |
| onboarding step1 | 768x900 | 0 | 768/768 | 900/900 | light |
| onboarding step1 | 375x812 | 0 | 375/375 | 812/812 | light |
| onboarding step1 | 1024x900 | 0 | 1024/1024 | 900/900 | dark |
| onboarding step1 | 375x812 | 0 | 375/375 | 812/812 | dark |
| onboarding step2（表单） | 1024x900 | 0 | 1024/1024 | 900/900 | dark |
| onboarding step3（转写器） | 1024x900 | 0 | 1024/1024 | 900/900 | dark |
| onboarding step4（收尾） | 1024x900 | 0 | 1024/1024 | 900/900 | dark |
| 404 | 1024x900 | 0 | 1024/1024 | 900/900 | light |
| 404 | 375x812 | 0 | 375/375 | 812/812 | dark |
| 启动失败 | 1440x900 / 1024x900 / 768x900 / 375x812 | 0 | 各等于视口宽 | 各等于视口高 | light ×3、375 dark |
| 错误边界 | 1024x900 / 375x812 | 0 | 1024/1024、375/375 | 900/900、812/812 | light、dark |

深色实测 canvas = `rgb(17, 23, 25)`（`--canvas #111719`），浅色 `rgb(244, 246, 247)`（`#f4f6f7`）；
深色靠 `localStorage['bilinote-theme']='dark'` 落地，不是靠 `prefers-color-scheme`（默认档位是 light）。

## 2. Onboarding 四步走通

步骤一探测 `/api/sys_check` 通过后「下一步」才可用；点它 → 步骤二填供应商名/Key → 「保存并下一步」
（实际文案是**保存并下一步**，不是「保存并继续」）→ 步骤三 → 「保存并下一步」→ 步骤四。
mock 依次应答 `/add_provider`→`prov-t072`、`/models`、`/connect_test`、`/transcriber_config`，四步均无 pageerror。
失败分支（后端未就绪时禁用下一步、显示重试）由 `tests/021-workbench-redesign/onboarding.test.tsx` 静态渲染盯住。

## 3. 启动等待与失败

| 状态 | 做法 | 观察 |
| --- | --- | --- |
| 等待 | route 挂起 `/sys_check` 永不回包 | `data-boot-state="loading"`，转圈 + 「正在启动后端服务」 |
| 轮询中 | `/sys_check` 回 503 | 同上，仍是等待态（不白屏，也不弹 toast） |
| 失败 | 503 撑满 60s 预算 | `data-boot-state="failed"`：标题「后端启动失败」+ 「后端在 60s 内未就绪，最后一次探测：HTTP 503」+ 三条常见原因 + 「重新检测」 |
| 重试 | 点「重新检测」 | 状态回到 `loading`（`stateAfterClick: "loading"`），说明重试入口真的接上了 |

## 4. 404 与键盘可达

- 1024 宽：Tab 第 1 下落到侧栏「工作区」，第 6 下落到 404 卡片里的「返回工作区」链路；焦点环实测
  `outline: 2px solid`（新加的 `focus-visible:outline-accent`）；回车后 URL 变回 `/`。
- 375 宽（抽屉态）：Tab 第 4 下到「返回工作区」，回车同样回 `/`。
- 见 `notfound-1024-focus.png`（焦点在图中的返回链接上）与 `notfound-1024-light.png`、`notfound-375-dark.png`。

## 5. 错误边界不白屏

启动屏与 404 之外，另用临时页面 `crash-t072.html`（不提交）把真实 `ErrorBoundary` 包住一个渲染即抛错的子组件：

```
{"rootChildren":1,"hasCard":1}
```

即崩溃后 `#root` 里仍有内容、`[data-boundary-state="error"]` 卡片在位：标题「页面遇到问题」、scope
`w4-harness`、红字 `Error: W4 错误边界触发验证：子组件渲染抛错`、「重试」「复制日志」两个入口。深色下同样成立。

## 6. 本轮改动

- `StartupScreen.tsx` / `OnboardingPage.tsx` / `NotFoundPage.tsx` / `ErrorBoundary.tsx` 的旧色名
  （`bg-primary`、`text-on-primary`、`bg-primary-soft`、`bg-ok`、`text-ink-mute`、`accent-[var(--primary)]`）
  统一换成 021 的规范名（`accent` / `on-accent` / `accent-soft` / `success` / `ink-muted`）。
  这些别名原本就指向同一批 CSS 变量，所以**视觉不变**，只是不再给兼容层续命。
- 404 的「返回工作区」链接补 `focus-visible:outline-2 outline-offset-2 outline-accent`。
- 新增 `tests/021-workbench-redesign/onboarding.test.tsx`（6 例）：启动屏两种状态、失败原因按 code 走 i18n、
  404 有 `href="/"` 与焦点样式、引导首屏不放行、四个面不再写回旧色名。
- 修掉一处过时注释（StartupScreen 的 "Terracotta tile + Playfair wordmark"）。

## 7. 与计划的偏差（需要知会）

计划里列的 `pages/OnboardingGuard.tsx`、`startup/StartupNotice.tsx`、`startup/useBackendEvents.tsx`
在本分支**不存在**：`6fc8d80 refactor: remove Tauri desktop target end to end` 已把它们删除（守卫逻辑并入
`EmberApp.tsx` 的 `useCheckBackend` 判定，不再有独立 Guard 组件；启动事件通道一并移除）。
因此验收 #2 的「hex 改 token」落在 `StartupScreen.tsx` 一个文件上——该文件本就没有裸 hex，本轮做的是色名归一。

## 8. 复现

1. `cd BillNote_frontend && pnpm dev --port 3036`，并设 `VITE_API_BASE_URL=http://127.0.0.1:8486/api`
2. 起任意后端 mock：`/api/sys_check` 回 `{code:0,data:true}`；`/add_provider` 回 `{code:0,data:'prov-t072'}`；
   其余业务接口回 `{code:0,data:null}`
3. Playwright：`/onboarding`（等「下一步」不再 disabled）、`/no-such-page-t072`、`/`（用 route 挂起或 503 撑 60s）
4. 错误边界：临时页面里 `createRoot(...).render(<ErrorBoundary><Boom/></ErrorBoundary>)`，Boom 直接 throw
