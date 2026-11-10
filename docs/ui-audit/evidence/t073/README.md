# T-073 · 扩展三面（popup / options / sidepanel）视觉与状态证据

运行方式：`pnpm build` 产出 `BillNote_extension/extension/`，Playwright 以
`launchPersistentContext` 加载解包扩展（`--load-extension`），页面地址
`chrome-extension://<id>/dist/{popup,options,sidepanel}/index.html`。
后端用 `context.route('http://localhost:8483/**')` 的 mock 提供
`/api/sys_check`、`/api/get_all_providers`、`/api/model_enable/*`、
`/api/generate_note`、`/api/task_status/*`。

## 真实尺寸与溢出

| 页面 | 视口 | scrollWidth/clientWidth | scrollHeight/clientHeight |
| --- | --- | --- | --- |
| popup | 400×600 | 400/400（浅色）/ 400/400（深色） | 600/600 |
| options | 1280×800 | 1280/1280（浅色）/ 1280/1280（深色） | 800/800 |
| sidepanel | 360×800 | 360/360（浅色）/ 360/360（深色） | 800/800 |

深色主题用 `emulateMedia({ colorScheme: 'dark' })`，实测 popup canvas 计算值
`rgb(17, 23, 25)`，等于 `--canvas: #111719`；浅色 `#f4f6f7`。

## 四态截图

| 状态 | 文件 | 判据 |
| --- | --- | --- |
| 空态 | popup-empty-light-400x600.png | 「还没有任务。选好供应商和模型后点『生成笔记』」+ 折叠的「最近任务」 |
| 就绪态 | popup-ready-light-400x600.png | 三个下拉 + 四个输出形式复选框 + 模型名 + 可点的「生成笔记」 |
| 加载态 | popup-loading-dark-400x600.png | 「转写中」badge + 分段进度条（深色） |
| 失败态 | popup-failed-light-400x600.png | 「失败」badge + 「转写失败：ASR 超时」+ 侧边栏入口 |
| 后端不可用 | popup-backend-down-400x600.png | 「后端不可用（HTTP 503），去设置后端地址」 |

失败任务不会在挂载时自动成为 activeTask（`Popup.vue:178` 只恢复未完成任务），
所以截图前必须点开「最近任务（N）」再选中该行。

## 键盘

popup 在 B 站视频页标签上下文下的 Tab 顺序（`document.activeElement` 逐次记录）：

```
打开设置 → 画质 → 笔记场景 → 笔记详略 → 目录 → AI 总结 → 原片截图 → 原片跳转
 → 高级（summary） → 生成笔记
```

在「生成笔记」上按 Enter：mock 返回 `task_id=t1`，`chrome.storage.local` 中出现
`taskId=t1 / status=TRANSCRIBING / title=键盘流程测试视频`，键盘路径完成真实提交。

## 触控目标

`--blink-settings=primaryPointerType=2,availablePointerTypes=2` 让 `(pointer: coarse)`
为真（值 1 / 4 仍为 fine）。12 个可交互控件的实测矩形：

```
设置 44×44 · 三个 select 44×113 · 四个复选框 44×13 · 高级 summary 44×354
· 去设置 44×44 · 生成笔记 44×354
```

（复选框本体 13px 宽但高度 44px，命中区域由整行 label 承担。）

## 与父卡一致性

扩展没有共享包，`src/styles/tokens.css` 手工镜像 Web 的 `ember/tokens.css`：
同名 `--canvas/--surface/--raised/--ink/--ink-soft/--ink-muted/--line/--line-strong/
--accent/--accent-soft/--on-accent/--success/--warning/--danger/--info`，同一套
动效阶梯（120/160/180/200/260/300ms），`--font-serif` 同样指向 Source Serif 4。
`src/__tests__/tokens.test.ts` 守住这几条不变量（含“tokens.css 之外不得出现 hex”）。

## e2e（BLOCKED）

`e2e/basic.spec.ts` 存在三条用例（example test / popup page / options page），
`pnpm test:e2e` 已验证能启动且确实执行了它们。失败点只有一个：本机 Playwright
1.46.1 要 `chromium-1129`，而 `%LOCALAPPDATA%\ms-playwright` 里只有
1148/1169/1181/1208/1234/1248。原样报错：

```
Error: browserType.launchPersistentContext: Executable doesn't exist at
C:\Users\Administrator\AppData\Local\ms-playwright\chromium-1129\chrome-win\chrome.exe
```

补跑：`cd BillNote_extension && pnpm exec playwright install chromium && pnpm test:e2e`。
（`pnpm exec playwright install chromium` 在本次会话里下载超时被中断，故未标记通过。）
