# Migration and regression gates

- Type: task
- Status: implemented（契约版本化、读时归一、回归闸门全绿、三端证据清单均已落地；旧表现层已删除）
- Depends on: 002-task-read-model-and-update-transport, 003-performance-baseline-and-budgets, 004-pipeline-deduplication-and-cache-seams, 005-i18n-contract-and-migration
- Blocks: implementation completion

## Question（原始问题，保留）

Define staged cutover and regression gate: schema/interface versioning, old task/config normalization, extension compatibility, feature flags or route migration, backend/frontend test locations, and desktop/tablet/mobile plus Chinese/English release evidence.

## 1. 契约版本化

- 新增接口全部带版本前缀：GET /api/v1/task-groups/snapshot、GET /api/v1/task-groups/events、POST /api/v1/intake/resolve。旧接口原样保留，不加前缀、不改形状。
- snapshot 响应带 schemaVersion（当前 1）。消费方读到不认识的 schemaVersion 应当**降级到轮询旧接口**，而不是猜字段 —— 版本号存在的意义就是让「不认识」变成可判定的，而不是解析到一半才炸。
- intake/resolve 接受可选的 contractVersion（缺省按 1 处理）。服务端只承诺同 major 内向后兼容：加字段不算破坏，改字段语义算。
- **不删旧接口**：扩展端（BillNote_extension）仍在用 /api/get_all_providers、/api/get_models_by_provider/{id}、/api/generate_note，并且自己拼 /static/screenshots/ 前缀。删掉它们等于让扩展静默坏掉。

## 2. 旧数据规范化：读时归一，不写迁移脚本

历史任务状态文件里的值不统一（中文状态、success / SUCCESS 大小写、phase 缺失）。处理方式是在**读时**归一，不批量改写磁盘：

- backend/app/services/task_read_model.py 的 normalize_status(value) 容忍 None、大小写、中文别名；
- normalize_phase(value, status) 遇到未知 phase 时按 status 推导，绝不把已成功任务判成 None；
- to_task_view(task_id, raw, revision) 是唯一的投影点，所有消费方（新前端、SSE、未来的桌面）看到同一份规范形状。

理由：迁移脚本一旦跑错就无法回滚，而归一函数有单测（backend/tests/017-web-rebuild-and-architecture/test_task_read_model.py）能一直钉住行为。代价是每次读都付一次归一开销 —— 可忽略（纯字符串比较）。

前端侧的对应约束：src/store/taskStore/index.ts 的 updateTaskStatus 拒绝 revision 倒退的更新，所以「旧页面残留的旧快照」不会覆盖新状态。

## 3. 路由与入口迁移：切换点只有一行

- src/main.tsx 只挂 EmberApp（StrictMode > EmberI18nProvider > EmberApp + EmberToaster）。旧 src/App.tsx 与新入口无关。
- 无 feature flag、新旧前端不并存：并存等于两套状态机抢同一份 zustand store 与同一份 IndexedDB，是最难查的一类 bug。切换点就是 main.tsx 里的一行 import。
- 旧表现层 79 个文件（src/pages 31、src/components 44、src/layouts 3、src/App.tsx 1）**已于用户确认后删除**（git rm -r -f + rm -rf，78 个已跟踪 + 1 个未跟踪）。删除前 grep 排除旧目录自身后无任何引用，且它们本就不参与构建 —— Vite 只从 main.tsx 可达图打包。
- 同一轮清掉的零引用死模块：src/store/{modelStore,providerStore,configStore,chatStore}（仅 taskStore 有 9 处引用）、src/data（旧 i18n 与 workspace facade，仅剩 useEmberNav 引用，已改走 ember 字典）、src/lib/utils.ts、src/utils/{fileName,index,markdown,progress,range,taskStatus,text}.ts、src/types/index.d.ts、src/App.css、src/indexa.css、src/assets/（全部 Lottie 与图标，零引用，图标实际走 public/icon.svg）。
- 删除后 src 只剩 11 个顶层条目：constant / ember / hooks / lib / services / store / types / utils / index.css / main.tsx / vite-env.d.ts。**这条清理让类型与 lint 从「不劣于基线」直接归零**（见 §4）。

## 4. 回归闸门（五条自动 + 一条人工）

| 闸门 | 命令 | 通过标准 |
| --- | --- | --- |
| 后端单测 | cd backend && .venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider | 全绿（当前 843 passed, 13 subtests passed） |
| 前端类型 | cd BillNote_frontend && pnpm exec tsc -b | **exit 0 且无 error TS**。HEAD a9db968 曾预存 106 条，删除旧表现层与死模块后归零；任何时候回退到「不劣于基线」都是退步，不是通过 |
| 前端构建 | cd BillNote_frontend && pnpm build | exit 0；index gzip 不劣化（删除死模块后 **148.89 kB**，清理前 155.95 kB） |
| i18n 契约 | cd BillNote_frontend && pnpm test:i18n | i18n contract OK — N keys, zh-CN and en-US aligned |
| 前端 lint | cd BillNote_frontend && pnpm exec eslint src | **exit 0 且 0 problems**。HEAD 时是 101（88 errors / 13 warnings），随旧表现层与死模块一并清除 |
| 三视口人眼 | scripts/ember-viewport-shots.cjs 后逐张 read_image | 每张 overflowX=none 且版式正确 |

五条必须记住的教训：

1. **后端全量必须真连跑**。已经发生过一次「单跑各目录全过、全量才炸」的跨模块污染（test_downloader_skip_download.py 的桩模块还原没进 finally，加载失败时把 app.services 永久换成裸模块，后续 46 个无关用例连锁失败）。「单跑绿」不是证据。
2. **`pnpm exec tsc --noEmit` 在本仓库是空操作，必须用 `pnpm exec tsc -b`**。tsconfig.json 是 solution-style（`{"files": [], "references": [tsconfig.app.json, tsconfig.node.json]}`），`--noEmit` 不解析 references，只编译 `files: []` 后正常退出 —— 探针验证过：注入 `const __probe: number = "definitely-not-a-number"` 仍 exit 0。所以「类型闸门绿」在本仓库从来不成立，唯一有效形式是与基线做逐文件比较（`src/ember` 必须为 0）。
3. **脚本只保证拍到了，不保证好看**。ember3-mobile-workspace.png 第一版就是人眼发现的：主按钮 flex-1 撑成整条、时间戳断成「9天 / 前」。所以人工闸门不能省，delivery_check 里 page/image 证据要求 reviewed:true 也是这个意思。
4. **lint 报错先问「这条规则在这里是不是本来就不适用」，别急着逐行 disable，也别急着改代码去迎合它**。`src/types/react-19-jsx-shim.d.ts` 里 7 条 `@typescript-eslint/no-empty-object-type` 是真的，但那 7 个空 interface 恰恰**必须**是空的 —— 空才是「纯别名」，用 `interface` 而非 `type` 才能让别的库往同一个全局命名空间里 merge。所以修法是在 eslint.config.js 里为 `src/types/**/*.d.ts` 单独关掉这条规则（并写明理由），而不是把 shim 改成 `type`（那会失去声明合并）或逐行加 disable。
5. **「不劣于基线」只是过渡标准，不是终点**。旧树有 106 条类型错和 101 条 lint 问题时，把闸门定成「不比基线更差」是唯一能推进的做法；但基线一旦降到 0（删掉旧表现层与零引用死模块就做到了），标准必须同步收紧成 exit 0 —— 否则下一次改动的 5 条新错误会藏在「仍优于 106」里溜过去。

## 5. 发布证据清单

- **三视口 × 9 路由**：scripts/ember-viewport-shots.cjs → C:/Users/Administrator/Downloads/ember3-<vp>-<route>.png（desktop 1440×900 / tablet 834×1112 / mobile 390×844；workspace 与 settings 八页）。
- **英文 × 3 视口 × 4 路由**：scripts/ember-en-shots.cjs → ember4-en-<vp>-<route>.png，预置 localStorage bilinote-locale=en-US，每张统计 overflowX 与 main 内是否残留中日韩字符。
- **启动失败面**：scripts/ember-boot-shots.cjs → ember-boot-<case>-{loading,failed}.png（zh/en × desktop/mobile），用 page.route abort /api/sys_check 造失败态。
- **首启引导**：scripts/ember-onboarding-shots.cjs → ember-onboarding-*.png（8 个 case，mock 掉 add_provider / models / connect_test / transcriber_config，**绝不写真实供应商或模型行**）。
- **批量导入与阅读器**：scripts/ember-batch-shots.cjs、scripts/ember-reader-shots.cjs。
- 截图运行环境：Playwright 用 chromium.launch({executablePath: C:/Users/Administrator/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe, args: [--no-sandbox]})，NODE_PATH 指向 npm-cache 里的 playwright。等待序列必须是 waitForSelector(main) → waitForFunction 无 [data-boot-state] → waitForTimeout(600)；裸等固定时长会拍到启动栅栏或空帧。

## 6. 扩展端兼容闸门

- 本次后端改动**只新增、未删除**旧接口，扩展走的三个接口形状未变。改路由前后各跑一次 curl 确认（/api/sys_check 与扩展实际调用的接口）。
- SUPPORT_PLATFORM_MAP 收窄到 bilibili 会让扩展里 youtube / douyin / kuaishou 入口失败 —— 返回明确错误而非静默跳过。这是**范围决策**（只保留 Bilibili），不是回归。
- Source Intake 保持平台无关形状（单条 URL 与批量 URL 两个入口），未来加平台只需加 adapter，不需要改扩展或前端的调用面。

**实测（2026-10-17，对 127.0.0.1:8483 逐个 curl）**：扩展实际调用的 7 个接口全部解析正常 —— `/api/get_all_providers` 200、`/api/deploy_status` 200、`/api/transcriber_config` 200、`/api/transcriber_models_status` 200、`/api/model_list` 200、`/api/sys_check` 200；三个 POST-only 路由 `/api/add_provider`、`/api/update_provider`、`/api/generate_note` 用 GET 探测返回 **405 而非 404**，说明路由存在（405 = 方法不允许，404 才是路由消失）。

顺带纠正一处**文档与代码不一致**（非本次回归，HEAD 即如此）：CLAUDE.md 写的是 `/get_models_by_provider/{id}`，实际路由是 `GET /api/model_enable/{provider_id}`（backend/app/routers/model.py:49，`git show HEAD:` 确认 HEAD 同款）。`/api/get_models_by_provider/1` 返回 404 属预期，扩展本身也没调用它。

## 7. 待确认问题

- 旧表现层 78 个文件何时删除？（已无引用、git 有基线可恢复，但删除不可逆，等用户确认。）
- 扩展端是否跟随 i18n？（当前不动，属另一个交付面。）
- 旧接口（/api/get_task_status 等）的兼容期到什么时候？当前无限期保留，因为扩展依赖它们。

## 8. 交付闸门的已知环境缺陷（2026-10-17 记录）

delivery_check 的 `page-verify` 一项在当前宿主上**无法通过**，与本仓库产物无关：

- `page-verify` 的 detail 原文：`visual verify the page with bash (headless Chrome/playwright screenshot) + read_image (reviewed:true) into evidence — delivery_check gates the evidence, not a built-in browser`。
- 它要求的证据我已经逐条提供并复核：`tools.ops_bash` 起 headless Chromium 截 `http://127.0.0.1:4174/`（dist-serve 托管的生产产物）→ `read_image` 人眼复核 → 把截图同时以 `kind=page` / `kind=image` + `reviewed:true` 塞进 evidence。结果 `delivery-evidence` PASS，`page-verify` 仍 FAIL。
- 试过的证据形状全部无效：page 指向本地 html、page 指向 http URL、page 指向截图、image 指向 Downloads、image 指向 dist 内、run + result 描述截图命令、external + result、run 同时带 target 与 result。
- 根因在宿主侧：该检查依赖名为 `bash` 的工具，而本会话 `tools.bash` 稳定抛 `ctx.shell.execute is not a function`（`tools.ops_bash` 与捆绑的 `@dsh-ops/bash-win32-x64/bin/bash.exe` 本身是好的，能正常执行）。这是宿主插件缺陷，不是可以靠改仓库修掉的东西。

**因此交付判定标准定为：其余四条闸门全绿 + page-verify 单独标注为环境阻塞。** 不能因为这一项就宣称整体 PASS，也不应该为它伪造证据。