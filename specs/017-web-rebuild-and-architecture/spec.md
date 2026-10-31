# 017 Web 重构与架构协同规格

> 状态：implemented（2026-10-17；旧表现层已删除，类型与 lint 归零）
> 来源：用户需求 m00002、m00046 与 wayfinder 地图 wayfinder/015-web-rebuild-architecture/README.md

## 1. 背景

BiliNote 当前包含 Bilibili 视频生成、合集/多 P 批量导入、任务进度、笔记预览、思维导图、转录查看、归档导出、历史分组、失败重试、聊天问答、模型/提供商、转写器、下载器、代理、媒体留存和系统监控等能力。近期提交已经优化了任务状态读取、启动路径和流水线局部耗时，但前端页面、请求编排和后端流程仍需要以同一个用户体验目标重新组织。

本需求不是单纯换肤：网页前端是唯一交付目标，前后端接口允许同步重塑；生成渠道收敛为 Bilibili，其他渠道从生成链路和页面中移除，同时保留平台无关的单视频 URL 与批量 URL 识别接口形状；界面暂时只覆盖中文和英文。

## 2. 目标

- 用 ember-studio-DESIGN.md 的 Ember Studio 设计系统重做网页信息架构和 UI/UX。
- 桌面、平板、手机均可完成输入 Bilibili 单视频/合集/批量 URL、选择参数、查看任务、阅读笔记、思维导图/转录、聊天、导出和设置。
- 通过更深的 module 和清晰的 interface 重新组织任务读取、来源识别、页面数据编排和流水线执行，提升 locality、测试能力和加载性能。
- 建立完整的中文/英文 i18n：界面文案、状态、错误、可访问性标签和设置项可切换；生成内容本身不翻译。
- 以可重复基线和体验预算验收加载速度、交互响应、请求数量、任务进度新鲜度和低带宽表现。

## 3. 非目标

- 不构建或验证 Tauri 桌面包。
- 不在本需求实现 YouTube、Douyin、Kuaishou 的生成 adapter。
- 不重做浏览器扩展 UI；只有共享后端 interface 被改动时才维护其兼容适配。
- 不为视觉重构改变提示词语义、笔记质量或 OCR 判定规则。

## 4. 已定决策

1. 交付物是网页重构的 approved spec、按依赖排序的实现 tickets，以及后续实现后的可验证网页；wayfinder 先完成路线，不直接修改业务代码。
2. 前后端同步重塑 interface，允许新增聚合读取、任务事件/增量状态和版本化契约；迁移期间必须有明确兼容策略。
3. 生成入口只显示并实现 Bilibili；URL 识别 module 保持 single 和 batch 两类平台无关结果，以便未来新增 adapter 不改变页面 interface。
4. Ember Studio 使用 terracotta #C2410C、amber #F59E0B、warm neutral、Playfair Display + Source Sans 3；避免装饰性视觉，优先清晰的任务工作流。
5. 性能采用体验预算制：先测现状，再锁定数字；不以“看起来更快”替代证据。

## 5. 当前能力清单与保留边界

| 能力 | 处理 | 说明 |
| --- | --- | --- |
| Bilibili 单视频、短链、分 P | 保留并重做 | URL 解析与 Bilibili downloader 是核心 seam |
| Bilibili 合集/系列、批量 URL | 保留并重做 | 保留 batch interface，提供组级进度和单项失败 |
| YouTube、Douyin、Kuaishou 生成 | 移除 | 移除页面选项、生成分支和本需求实现 adapter |
| 下载、字幕/ASR、采样、OCR、LLM、Markdown | 保留并优化 | 保留产出语义，合并可安全复用的工作 |
| 任务队列、进度、重试、限流退避 | 保留并重做读取面 | 统一状态 read model，避免页面拼装多个来源 |
| 历史、分组、删除、归档导出 | 保留 | 按需加载和渐进渲染，不阻塞首屏 |
| 思维导图、转录、聊天问答 | 保留 | 重型渲染和 RAG 资源不阻塞首屏 |
| 提供商、模型、转写器、下载器、代理、监控、提示词 | 保留 | 设置模块懒加载并完整 i18n |

## 6. 目标架构方向

### 6.1 前端

页面组织为轻量工作区壳、任务工作台、历史/归档视图和设置模块。页面只依赖面向用户任务的 query/mutation interface，不直接知道 Axios、轮询间隔、后端字段或平台分支。Markdown、Markmap、聊天和设置面板按路由或交互懒加载，首屏只加载工作台所需模块。

### 6.2 任务读取 module

将生成、批量组、进度、重试和历史的读取模型集中在任务 module。后端提供版本化的任务摘要、批次摘要和增量状态 interface；前端以单次首屏快照加增量更新驱动 UI。具体采用 SSE、长轮询或优化后的短轮询由决策票据确定。

### 6.3 来源识别 module

把 single 与 batch 识别结果做成平台无关 interface，Bilibili 是当前唯一 adapter。页面只处理识别结果和校验错误，不把 URL 正则、短链解析和合集展开逻辑散落在表单中。

### 6.4 后端流水线 module

以任务阶段为稳定 interface，审查下载、字幕/ASR、采样/OCR、索引、LLM、导出和清理的重复工作。缓存和并行只放在语义不变且可观测的位置；共享缓存必须有任务隔离、媒体生命周期和失败重试语义。

## 7. 接口草案（非最终协议）

~~~text
POST /api/intake/resolve
  { mode: single | batch, urls: string[] }
  -> { items: [{ source, kind, canonical_url, video_id, parts?, state, error? }] }

POST /api/tasks
  { items, note_options, transcript_options, output_options }
  -> { group_id, tasks: [{ task_id, state, summary }] }

GET /api/task-groups/{group_id}/snapshot
  -> versioned group summary + task summaries + capability flags

GET /api/task-groups/{group_id}/updates?after={version}
  -> incremental state changes or documented fallback response
~~~

上面只固定用户任务语义，不固定 transport；错误必须包含稳定 code、可翻译 message key 和调试 detail。扩展接口不得要求前端知道具体来源 adapter。

## 8. 响应式与 i18n 验收方向

- 手机：单列工作流，底部/抽屉承载导航和次要详情，核心 CTA 在拇指可达区域；任务进度不依赖 hover。
- 平板：双栏工作台，任务列表与内容预览可并列；设置和聊天使用可调整面板。
- 桌面：侧边导航、主工作区和可选详情栏；正文阅读线保持受控宽度。
- 中文和英文切换不改变布局稳定性；长英文标签、错误详情和空状态不能溢出或遮挡。
- 语言包按命名空间拆分，禁止业务 JSX 新增裸露用户文案；后端错误使用 message key。

## 9. 测试要点

- 识别：Bilibili BV、b23.tv、分 P、合集/系列、单 URL、批量 URL、空值和非支持来源；Source Intake 决策见 wayfinder/015-web-rebuild-architecture/tickets/007-source-intake-module.md。
- 任务：单任务/批量组、重启恢复、重复提交、失败重试、429 退避、删除守卫、状态版本乱序和断线恢复；任务读取模型决策见 wayfinder/015-web-rebuild-architecture/tickets/002-task-read-model-and-update-transport.md。
- 流水线：字幕命中时不重复下载音频；采样/OCR/截图/索引的缓存命中与失败回退；输出与现有回归基线一致。
- 前端：首屏不加载 Markmap/聊天/设置重型依赖；中英文切换；三种 viewport；键盘和屏幕阅读器关键路径。
- 契约：前后端 schema、message key、能力 flag、批量组状态和扩展调用保持版本化测试。
- 性能：冷/暖缓存、桌面/平板/手机、快速/慢速网络、首屏请求数、关键资源体积、LCP/INP/CLS、任务进度延迟。

## 10. 已决问题（原「待确认问题」，2026-10-17 全部拍板）

- **任务更新 transport**：SSE 优先 + 带 `since` 游标的轮询兜底（`GET /v1/task-groups/events` 与 `/v1/task-groups/snapshot`）。决策见 wayfinder/015-web-rebuild-architecture/tickets/002-task-read-model-and-update-transport.md。
- **首屏与交互预算基线**：数字与 manualChunks 拆分记录在 wayfinder/015-web-rebuild-architecture/tickets/003-performance-baseline-and-budgets.md；当前 index gzip 约 156 kB、CSS gzip 约 23 kB、markdown 分包 gzip 约 280 kB（按需加载）。
- **接口迁移窗口与版本号**：新增接口一律 `/api/v1/...` 前缀并带 `schemaVersion` / `contractVersion`；旧接口无限期保留（扩展端仍在用）。见 wayfinder/015-web-rebuild-architecture/tickets/006-migration-and-regression-gates.md。
- **跨任务缓存边界**：只共享**转写**（按 video_url + 引擎键做 sha256 短哈希），不共享音频 —— 音频缓存存绝对路径，媒体清理会删文件，共享它等于让 A 任务的清理打穿 B 任务。坏缓存一律按 miss 处理，不让任务失败。隐私边界：只落本机 `NOTE_OUTPUT_DIR/shared/`，与任务级缓存同盘同权限，前提是单机单用户。见 wayfinder/015-web-rebuild-architecture/tickets/004-pipeline-deduplication-and-cache-seams.md。

剩余未决（不阻断交付）：扩展端是否跟随 i18n、`OCR_STAGE_CONCURRENCY` 默认值是否随基线调整。旧表现层 79 个文件已于用户确认后删除，同时清掉零引用死模块（4 个 store、`src/data`、`src/lib/utils.ts`、7 个 `src/utils` 文件、`src/types/index.d.ts`、`src/App.css`、`src/indexa.css`、`src/assets/`），`tsc -b` 与 `eslint src` 因此从「106 / 101 条基线」直接归零。

## 11. 实现清单

- [x] 001 能力清单与响应式信息架构（已完成前置盘点；实现设计由 008 承接）
- [x] 002 任务 read model 与更新 transport（已设计并实现：`backend/app/services/task_read_model.py`、`GET /v1/task-groups/snapshot`、`GET /v1/task-groups/events` SSE）
- [x] 003 性能基线与体验预算（已测基线并做 manualChunks 拆分，数字记录在 ticket）
- [x] 004 后端流水线重复工作与缓存接缝（全部落地：缓存接缝 `backend/app/services/note_cache.py`、OCR 阶段两段式并发 `OCR_STAGE_CONCURRENCY`、跨任务共享转写 `shared_transcript_path`、阶段入口单次读盘 `cache_checked`、音频缓存合并 `_remember_audio`；`backend/tests/017-web-rebuild-and-architecture/test_note_cache.py` 19 条用例）
- [x] 005 i18n 契约与迁移（已落地：`src/ember/i18n/strings.ts` 扁平字典 350 键、`translate()` 供非 React 模块、后端错误按 `data.reason` 查 `REASON_KEYS`、契约闸门 `BillNote_frontend/scripts/i18n-contract.cjs`（`pnpm test:i18n`）、英文三视口截图脚本 `scripts/ember-en-shots.cjs`；扩展端文案仍为中文，属独立交付面）
- [x] 006 迁移与回归闸门（已落地：`/api/v1/...` 版本前缀 + `schemaVersion` / `contractVersion`、读时归一不写迁移脚本、五条自动闸门（后端全量 pytest / `tsc -b` / `pnpm build` / `pnpm test:i18n` / `eslint src`，全部要求 exit 0）加一条人工闸门（三视口逐张 read_image）、发布证据清单与扩展端兼容闸门；旧表现层与零引用死模块已删除，类型与 lint 归零）

### 回归修复（2026-10-17）

实现 004/007 期间把下载器签名默认值从字符串 `"fast"` 改成枚举成员 `DownloadQuality.fast`（`backend/app/downloaders/base.py`、`backend/app/downloaders/bilibili_downloader.py`），撞上了三个测试文件里 `DownloadQuality=str` 的桩：`type object 'str' has no attribute 'fast'`。

其中 `backend/tests/006-note-pipeline-performance/test_downloader_skip_download.py` 与 `backend/tests/006-note-pipeline-performance/test_local_audio_from_video.py` 的 `_load_bilibili_downloader()` 在 `exec_module` 抛错时不会还原 `sys.modules` 桩，`setUpClass` 把异常转成 SkipTest，于是 `app` / `app.services` 等以「无 `__path__` 的裸模块」形态残留在进程里，后续 46 个无关用例连锁失败（`AttributeError: module 'app' has no attribute 'services'`、`ModuleNotFoundError: No module named 'app.services.ocr_test_image'; 'app.services' is not a package`）。

修复：三个文件（上述两个 + `backend/tests/test_ydl_retry_opts.py`）改用带 `fast` / `medium` / `slow` 的 `_DownloadQuality` 桩；两个 loader 的还原动作移入 `finally`，加载失败也必还原。全量后端测试恢复为 `837 passed`（818 旧 + 19 新增）。

### 生产构建深链白屏（2026-10-17，ticket 006 人工闸门发现）

`pnpm build` 的产物用 `base: './'` 生成相对资源路径。Web 部署（nginx / docker-compose）对所有路由都返回同一份 `index.html`，于是相对路径按当前 URL 解析：直接访问 `/settings/general` 时浏览器请求 `/settings/assets/index-*.js`，服务器把 `index.html` 当 200 返回，模块解析失败，页面空白。只有 `/` 正常 —— 开发服务器（Vite 自己处理路由）和点击式导航都掩盖了这一点，只有「生产产物 + 直接深链」才会暴露。

修复：`BillNote_frontend/vite.config.ts` 的 `base` 改为按 `mode` 决定 —— `mode === 'tauri' ? './' : '/'`。Web 用绝对根路径；Tauri 仍用相对路径（它从 app 资源协议加载，不经过 HTTP 路由）。键选 `mode` 是因为 `src-tauri/tauri.conf.json` 的 `beforeBuildCommand` 就是 `pnpm build --mode tauri`，不需要打包方记得多传一个环境变量。

验证：`dist/index.html` 中 Web 构建为 `/assets/index-*.js`、`--mode tauri` 构建为 `./assets/index-*.js`；`BillNote_frontend/scripts/dist-serve.cjs`（静态服务 + `/api`、`/static` 反代）下 `/`、`/settings/general`、`/settings/model` 三个深链 `mainCount` 均为 1。

### 结构化错误 reason（2026-10-17，ticket 005）

首启引导曾用 `errorText(e).includes('已存在')` 判断「供应商重名」：判定绑死中文文案，而且模型重名分支永远匹配不上（`POST /models` 无论重名还是其它失败都只回「模型添加失败」）。

修复：`backend/app/exceptions/provider.py` 新增 `ProviderNameExistsError(ValueError)`；`backend/app/routers/provider.py` 重名回 `code=400, data={'reason': 'provider_name_exists'}`；`backend/app/services/model.py` 新增 `create_model_outcome()` 返回 `created` / `exists` / `provider_missing` / `failed`，`add_new_model` 压成 bool 保持兼容；`backend/app/routers/model.py` 重名回 `data={'reason': 'model_name_exists'}`。前端 `OnboardingPage.tsx` 改用 `errorReason(e)`，`src/utils/request.ts` 的 `REASON_KEYS` 增加两条映射。契约由 `backend/tests/017-web-rebuild-and-architecture/test_error_reason_contract.py`（6 条）钉住。全量后端测试 843 passed（837 + 6）。

- [x] 007 来源识别与 Bilibili 收敛（已设计并实现：`backend/app/services/source_intake.py`、`POST /v1/intake/resolve`）
- [x] 008 前端数据层、i18n 与 Ember Studio 壳层（已设计并实现：`src/ember/**` 全量重写，未复用旧组件代码）

### 采样设置重设计 + 任务分组恢复（2026-10-17，用户复检发现）

重写时丢掉两块能力，用户复检时指出：

**采样设置**：`IntakeForm.tsx` 对 interval / smart / hybrid 三种模式渲染了同一套控件，于是 interval 下同时出现「抽帧间隔」和「每秒帧数」—— 两个控件在争同一批帧。而 smart / hybrid 各自的「帧数上限方式」「最大抽帧数」又缺失，`grid_size` 更是只剩 schema 没有输入框。修复按后端语义分派（`backend/app/services/note.py` 第 318–321 行 docstring）：interval 只留 `video_interval`；smart 留 `frame_limit_mode` + 按 total/per_second 二选一的 `max_frames`/`frames_per_second`；hybrid 只留 `max_frames`（它比 smart 多一次 `_plan_frames_with_llm` 选帧）。三种模式各配一句差异说明，`grid_size` 与 `ocr_assist` 移回视频理解区内并常驻显示 —— 后端第 517 行对三种模式都会把 `grid_size` 传给 `VideoReader`，藏起来等于让用户没法控制拼图密度。

**任务分组**：`src/ember` 里一个分组组件都没有，历史栏的注释还写着「grouping is a label rather than a nested tree」。旧版在 `HEAD:BillNote_frontend/src/pages/HomePage/components/GroupPanel.tsx`（343 行）与 `History.tsx`（618 行）。恢复为 `src/ember/features/workspace/GroupPanel.tsx` + `useNoteGroups.ts` + `archive.ts`（`sanitizeFileName` / `saveBlob` 随旧 `src/utils/fileName.ts` 一起被删过）：新建 / 重命名 / 删除（二选一「同时删除组内笔记」）/ 点击聚焦过滤 / 拖拽归档 / 下载选中分组的 zip。拖拽是历史栏卡片的 `draggable` 路径，`TaskList` 的选择模式另外提供「移动到分组」Dialog —— 触屏和键盘没有拖拽，这条路径不能只留一个。

**顺带修掉的真实后端缺陷（SSE 饿死线程池）**：`GET /v1/task-groups/events` 原本是同步 `def` + `time.sleep(1)` 循环最多 300 秒，Starlette 把同步生成器放在有界 worker 池里迭代，每条打开的流占一个线程整整 300 秒。前端 EventSource 断开重连不断新建流，池被占满后所有同步路由（`/api/note_group`、`/api/task_list`，都是同步 def + SQLite）排队挂死，而这个端点自身完全健康 —— 表现为「点新建分组报网络错误，但 `/api/sys_check` 一直是 200」。改成 `async def` + `await asyncio.sleep(1)` + `await request.is_disconnected()` + `run_in_threadpool(read_snapshot)`，前端 `useTaskPolling` 的 SSE effect 依赖从 `[tasks]` 收窄到派生的 `pendingKey`，并在快照全部终态时主动 `stop()`（否则 EventSource 会永久重连）。并发 60 条流下 `/api/note_group` 仍 200（308 ms）。回归由 `backend/tests/017-web-rebuild-and-architecture/test_task_read_model.py` 的 `test_task_group_events_handler_is_async` 与 `test_task_group_events_streams_a_first_snapshot_without_blocking` 钉住。

验收：`tsc -b` 0 错误、`eslint src` 0 problems、`pnpm build` exit 0（index gzip 154.76 kB）、i18n 契约 384 键对齐、后端 845 passed；截图 `scripts/ember-groups-shots.cjs`（三模式 + 分组面板 + 拖拽归档 + 移动端 + 英文）与 `scripts/probe-group-actions.cjs`（新建 → 移入 → 重命名 → 下载 zip → 删除）全部人工复核。

### 图片渲染、脑图/问答下线、内置供应商下线、转写引擎收敛、模型与转写配置可编辑（2026-10-17，用户复检第二轮）

用户提出五项，逐条落地：

**1. 笔记区图片渲染。** 排查结论：渲染器从未坏，是那条真实任务的 markdown 里一张图都没有（`grep -c '!\['` = 0）。但存在真实差异 —— 旧版 `HEAD:BillNote_frontend/src/pages/HomePage/components/MarkdownViewer.tsx` 第 178–181 行会把 `/static/...` 前缀成后端绝对地址，新版 `MarkdownNote.tsx` 原样透传。Web 部署下 nginx 的 `location /static/` 会反代到后端所以看不出问题，但桌面端（Tauri）页面 origin 是 app 资源协议，`/static/...` 无处可去，图会全裂。修复：新增 `src/ember/lib/assets.ts` 的 `resolveAssetUrl()`（绝对 URL / 协议相对 URL 原样返回，`/` 开头拼 `ASSET_ORIGIN`，后者由 `VITE_API_BASE_URL` 去掉 `/api` 后缀得到，所以 `http://host:8483` 与 `http://host:8483/api` 两种写法都对），并在 img renderer 上补回旧版的点击放大（`react-medium-image-zoom` 的 `Zoom`，`wrapElement="span"` —— 该版本的 `UncontrolledProps` 没有 `wrapProps`，间距改由外层 span 承载）。

**2. 脑图 + AI 问答整体下线。** 前端删 `src/ember/features/reader/MindMap.tsx`、`src/lib/markmap.ts`、`src/ember/features/chat/ChatPanel.tsx`、`src/services/chat.ts`；`NotePanel.tsx` 的 `ReaderTab` 收窄为 `'note' | 'transcript'`；`vite.config.ts` 去掉 markmap 的 manualChunks。后端删 `routers/chat.py`、`services/chat_service.py`、`services/chat_tools.py`、`services/vector_store.py`，`app/__init__.py` 摘掉路由，`routers/note.py` 删掉生成完成后的 `index_task_in_background(task_id)` 调用，`requirements.txt` 去掉 `chromadb>=0.5.0`。对应测试一并删除。

**3. 内置供应商下线。** 删 `backend/app/db/builtin_providers.json`（7 条：openai / deepseek / qwen / Claude / gemini / groq / ollama）与 `provider_dao` 里的 `get_builtin_providers_path()`、`seed_default_providers()`，`main.py` 的启动第 4 步不再 seed。`services/model_fallback.py` 去掉 `builtin_fallback_models()`：动态拉取失败时不再「假装成功」，而是把真实报错带回设置页。**已有数据库里的 7 条 built-in 行需要一次性清理**（seed 已删，它们不会自己消失），本次用 `delete from providers where type='built-in'` 清掉，清前备份为 `backend/bili_note.db.bak-20261017174314`。

**4. 转写引擎收敛为两条。** 删 `transcriber/groq.py`、`bcut.py`、`kuaishou.py`、`mlx_whisper_transcriber.py`；`TranscriberType` 只剩 `FAST_WHISPER` 与 `OPENAI_ASR`，`config.py` 的 `AVAILABLE_TRANSCRIBER_TYPES`、`get_transcriber_models_status()`（只回 `{"whisper": ...}`）、`download_transcriber_model()`、`sys_health` / `deploy_status` 的 mlx 分支同步收窄；`transcriber_config_manager.is_model_ready()` 的本地模型判定改为「非 fast-whisper 一律视为无需下载」。

**5. 模型配置与转写端点可编辑。** 两处都是真实缺口：模型页只能新建供应商、看不到也改不了已存的 base_url / api_key；转写页的 `updateOpenaiAsr` 服务函数一直存在但 UI 从未调用（用户说的「现有接口点击打不开修改」）。修复：
- `GET /api/get_all_providers` 改为返回打码后的 api_key（`serialize_provider_safe`），编辑对话框的 key 输入框默认留空、placeholder 显示掩码，空 = 不修改 —— 后端 `update_provider` 本来就会丢弃含 `*` 的值，所以掩码永远不会覆盖真 key。
- `ProviderDialog` 同时服务新建与编辑（同一套字段）；`ModelSection` 的供应商行是展开按钮，编辑是行内独立的铅笔按钮（按钮不能嵌套，否则两边的键盘激活都会坏）。
- `ProviderModels` 增加「从服务商获取」：按需调 `GET /api/model_list/{provider_id}` 走供应商真实 `/v1/models`，结果放进**可滚动且可搜索**的面板（该供应商返回 121 个模型，不设上限会把卡片撑到几千像素高），逐个「添加模型」；手填输入框保留 —— 不少网关不实现 `/models`。
- `TranscriberSection` 的每个端点补上铅笔与垃圾桶：编辑复用 `POST /openai_asr/{endpoint_id}`，删除走确认 Dialog。引擎下拉的文案改由前端字典提供（后端 `available_types` 的 label 只有中文，英文界面会漏出中文）；「模型规格」这一行只对 fast-whisper 显示 —— 在线端点没有本地模型可下。

验收：`tsc -b` 0 错误、`eslint src` 0 problems、`pnpm build` exit 0（index gzip 159.38 kB）、i18n 契约 393 键对齐、后端全量 833 passed（比上一轮少 12 条：删掉的 chat / vector / bcut / 内置清单用例）。截图与探针：`scripts/probe-settings.cjs`（供应商编辑对话框预填 + ASR 端点编辑对话框预填，中英各一遍）、`scripts/probe-remote-rows.cjs`（120 行模型全部有名字、无空行）、`scripts/probe-note-image.cjs`（图片 1280×410 加载完成、点击放大生效）、`scripts/probe-reader-tabs.cjs`（阅读器只剩「笔记 / 转写」两个 tab）、`scripts/probe-dist-settings.cjs`（生产产物下两个设置页正常）。全部人工复核。

### 浏览器扩展跟随清理（2026-10-17，与上节同一轮）

前端与后端下线脑图 / 问答 / 内置供应商 / 旧转写引擎之后，扩展端仍留着对应的死功能，属同一轮遗漏：

- **侧边栏的脑图与 AI 问答是死功能**：`src/sidepanel/Sidepanel.vue` 仍渲染 `MindMap.vue` 与 `ChatPanel.vue`，而后两者调用的 `/api/chat/index`、`/api/chat/status`、`/api/chat/ask` 已经随 `backend/app/routers/chat.py` 一起删除。删掉两个组件（156 + 181 行）、`src/logic/api.ts` 的 RAG Chat 客户端整段、`src/components.d.ts` 的自动导入声明，`Sidepanel.vue` 收成只渲染 Markdown（复制 / 下载保留）。`package.json` 的 `markmap-lib` / `markmap-view` 一并移除。
- **转写类型收窄**：`src/logic/types.ts` 的 `TranscriberType` 从六个值收为 `'fast-whisper' | 'openai-asr'`，删 `mlx_whisper_available` 与 `TranscriberModelsStatus` 的 mlx 两项（后端现在只返回 `{ whisper: [...] }`）；`src/options/pages/Transcriber.vue` 的 `isWhisperLike` 只判 fast-whisper，去掉 mlx 分支与那句「请改用 fast-whisper / Groq / 必剪 / 快手」的过时提示。
- 平台枚举（`Platform` 里的 youtube / douyin / kuaishou）**保留不动**：扩展是独立交付面，识别到非 Bilibili 链接时给出明确提示比静默失败好；是否收窄留给用户决定。

验收：扩展 `tsc --noEmit` exit 0、`vitest run` 2 files / 2 tests passed、`vite build --mode production` exit 0；`grep -rn "markmap|ChatPanel|MindMap|chat/index|chat/ask|mlx" src/ package.json` 无命中。

踩坑记录：`package.json` 删依赖时把最后一个 `"markdown-it": "^14.1.0",` 留成尾逗号，vitest 直接以 `[ERROR] JSON does not support trailing commas` 拒绝启动 —— JSON 改完必须 `json.loads` 验证。`Sidepanel.vue` 按行号切片时把结尾的失败提示块留了两份，Vue 编译器报 `Invalid end tag`，且该文件是 CRLF，切片前必须先归一成 `\n` 再换回。

### 「有插图位置却没有图片」的两个后端缺陷（2026-10-17，用户复检第三轮）

用户追问「图片渲染修好了吗 / 为什么有插图位置却没有图片」。上一轮只修了渲染器（`resolveAssetUrl` + `Zoom`），而真实任务 `1d994afa-a36c-4861-b4b9-f83d7d5beb12` 的 markdown 里是 **31 个 `[[SHOT-n]]` 占位符 + 0 张图** —— 渲染器没问题，是后端根本没插图。两个独立成因：

**成因 1：音频缓存命中时 `self.video_path` 永远为空。** `NoteGenerator._download_media`（`backend/app/services/note.py`）在缓存命中分支直接 `return cached`，而 `self.video_path` 的唯一赋值点在真正下载的分支里。于是 `_post_process_markdown` 的 `if "screenshot" in formats and video_path:` 判 False，`_insert_approved_screenshots` 整步**静默跳过**（连一行日志都没有）。这不是边角情况 —— 「第二次生成同一个视频」是最常用的路径，用户看到的是一排没被替换的占位符。修法：新增 `_adopt_video_path(audio, *, downloader, video_url, output_dir, task_id)`，查找顺序 `audio.video_path` → `<output_dir>/<video_id>.mp4` → 重调 `downloader.download_video`（命中已存在文件会直接返回，不重复下载）；`need_video = screenshot or video_understanding` 提到缓存分支之前，只有真的要图时才去找视频。

**成因 2：复用 OCR 磁盘缓存时模型一张图都没看到。** 判定结果（哪些画面值得编入笔记）会落盘复用，但图片本身不在缓存里（data URL 太占地方）。于是 `_summarize_text` 的 `prompt_img_urls` 为空、`image_count=0`，模型在没看到任何画面的情况下被要求写 `[[SHOT-n]]`。修法：新增 `_render_shot_frames(video_path, task_id)` 统一负责「判定通过的每张图渲成单帧 + 登记 media_resource + 转 data URL」，幂等（`shot_frames` 长度一致且文件都在就复用）；OCR 复用分支、`_run_ocr_stage`、`_insert_approved_screenshots` 三处都改走它 —— 以前总结与后处理各自渲一遍，白跑一遍 ffmpeg 还在磁盘上留没人引用的副本。

**兜底：占位符不能再漏给用户。** `_post_process_markdown` 拿不到视频路径时打 warning「需要插图但拿不到本地视频路径，本轮跳过插图」，返回前用模块级 `_SHOT_MARKER_ANY = re.compile(r"\[\[\s*SHOT\s*-?\s*\d+\s*\]\]", re.IGNORECASE)` 清扫残留占位符并记条数 —— 模型多写编号是常态（这次就多写了 1 个）。另外 `generate()` 在 `prepend_source_link` 之后把**最终** markdown 写回 `note_results/<task_id>_markdown.md`，此前缓存里存的是未插图版本。

**验证**：新增 `backend/tests/017-web-rebuild-and-architecture/test_screenshot_pipeline.py`（8 条，`object.__new__(NoteGenerator)` 构造，不初始化转写器）钉住缓存命中找回视频路径 / 视频丢失时重下 / 不需要图时不下视频 / 渲染幂等 / 后处理复用已渲染帧 / 无视频时清占位符 / 模型多写时清占位符 / 无判定结果时不渲染。后端全量 841 passed。

端到端用真实任务复跑（走生产入口 `routers.note.run_note_task`，含 `save_note_to_file`，耗时 376.8 s）：日志出现「音频缓存命中，已恢复视频路径：data\BV1Rch76WEfQ.mp4」「截图单帧渲染完成：判定通过=30 实际出图=30」「正文残留 1 个未替换的截图占位符，已移除」；`note_results/1d994afa-....json` 从 0 图 31 占位符变成 **30 图 0 占位符**，`GET /api/task_status/{id}` 同步返回 30 图。前端探针 `scripts/probe-fixed-note.cjs` 实测 `main img` total=30、首图 1280×410 加载完成、`[[SHOT` 计数 0、点击放大 `[data-rmiz-modal]` 出现；截图 `reader-fixed-viewport.png` / `reader-fixed-zoom-viewport.png` 人工复核。

复跑工具留在 `backend/tools/`：`verify_screenshot_fix.py`（不起 LLM，只跑下载/缓存/渲染/后处理四段）与 `e2e_regenerate.py`（完整复跑一条真实任务，含落库）。

### 可配置的事务边界（2026-10-17，用户新需求）

用户原话：「还要加入 asr 的最大文件大小，最多多少分钟。全局设置里需要多一个配置项是否按照静音进行拆分——静音阈值之类的拆分选项……还有 llm 也需要标记最大请求体大小（比如只能 30m 的图片之类的），你看一下后端事务有哪些需要配置的现在缺少的全部补上。」

**问题不是「没有配置」，而是「配置埋在代码里」。** 三个典型：ASR 端点的 `silence_split` / `silence_noise_db` / `min_silence_seconds` 在 `transcriber_config_manager.py` 里早有字段和校验，但设置页一个都没暴露（`grep src/ember silence_split` 零命中）；LLM 的请求体预算硬编码在 `universal_gpt.py` 的 `GATEWAY_MAX_REQUEST_BYTES = 9 MiB`；OCR 阶段并发硬编码成 `OCR_STAGE_CONCURRENCY = 4` 的环境变量。用户遇到 413 / 429 / 切段不合理时，除了改代码没有别的出路。

**决策 1：新增一层运行时门面，不让业务代码直接读 DB。** 新建 `backend/app/services/runtime_limits.py` 作为唯一读取入口：5 秒 TTL 缓存（`_CACHE_TTL_SECONDS = 5.0`，`threading.Lock` + `_cached` / `_cached_at`），读库异常一律 warning + 回落常量（配置坏了不能让生成任务挂掉），`reset_cache()` 供写入路径和测试失效 —— `general_settings_dao.update_general_settings` 保存后立刻调用，所以「保存即生效」不需要等 TTL。

**决策 2：环境变量优先于数据库。** 部署方用 env 锁死网关上限时，不该被界面上的一次手滑改掉。因此 `llm_gateway_ceiling_bytes()` 读的是纯 env 值（`OPENAI_GATEWAY_MAX_REQUEST_BYTES`，默认 9 MiB），用户配置只能在这个天花板之下调整。

**决策 3：用户预算不能突破网关天花板，而不是取两者最大值。** 一开始写成 `max(env, 用户配置)`，立刻被既有测试打回（`tests/008-.../test_ticket02_flow.py:1010` 断言 `gpt.max_request_bytes == GATEWAY_MAX_REQUEST_BYTES`）。想清楚后改成 `min(用户配置, env 天花板)`：超过网关硬上限的请求会回 413 `request body too large`，而 413 **不在可重试清单**里 —— 让界面把预算调到 30 MiB 只是把失败从「预算太小」推迟成「线上 413」。要更大上限请改 env，那是部署决策。

**决策 4：判定层的图片预算必须独立配置，且必须显著低于请求体上限。** `llm_judge_image_budget_bytes()` = `min(配置值, min(llm_max_request_bytes(), gateway_ceiling) - 1 MiB)`。原因写在设置页的 hint 里：大请求会被网关**直接断连**，返回的错误信息会误导成「模型不存在」，排障时极难联想到体积。

**新增的 11 个可配置项**（`backend/app/db/models/general_settings.py`，全部 nullable=True 兼容老库，布尔存 Integer 0/1）：`asr_max_file_mb`（0 = 不限）、`asr_max_duration_minutes`（0 = 不限）、`asr_silence_split`、`asr_silence_noise_db`（-80 ~ -5）、`asr_min_silence_seconds`（0.05 ~ 30）、`llm_max_request_bytes`（256 KiB ~ 128 MiB）、`llm_judge_image_budget_bytes`、`llm_retry_attempts`（1 ~ 10）、`llm_retry_backoff_seconds`（0 ~ 60）、`ocr_stage_concurrency`（1 ~ 32）、`note_max_images`（1 ~ 500）。迁移写在 `backend/app/db/init_db.py` 的 `_settings_additions` 元组循环里，与既有 `general_settings` 逐列 ALTER TABLE 同一套写法。

**消费点全部改成读门面**：`universal_gpt.py`（新增模块级 `gateway_max_request_bytes()`，每次重读 env 以便测试改 env 生效；`max_request_bytes = min(用户配置, ceiling)`；重试次数与退避基数；判定图片预算；`note_max_images`）、`ocr_assist.py`（`max_note_images()` / `max_judge_candidates()` 取代常量）、`note.py`（`max_workers` 走 `ocr_stage_concurrency()`）、`transcriber_config_manager.py`（端点默认值取全局 `asr_*`，端点显式配置仍优先）。模块常量 `GATEWAY_MAX_REQUEST_BYTES` / `JUDGE_IMAGE_BUDGET_BYTES` / `OCR_STAGE_CONCURRENCY` / `MAX_NOTE_IMAGES` 全部**降级为兜底**并加注释指向门面 —— 保留是因为 `tests/008` 仍在 import 并断言它们的关系。

**ASR 输入闸门**：`runtime_limits.asr_input_violation(file_path)` 做两道检查（体积 + `probe_duration_seconds` 时长），越界返回中文说明并指向「设置 → 通用」。调用点放在 `_transcribe_audio` 的**缓存检查之后** —— 命中缓存根本不会调用 ASR，此时因为超限拒绝任务纯属误伤。

**前端**：`src/services/general.ts` 扩 11 个字段 + 伴生 `_default` / `_limit` / `_min` / `_max`（前端不抄常量，上下界一律后端下发）；`GeneralSection.tsx` 按「保护什么」分成 4 组（任务与缓存 / 音频转写输入 / 大模型请求 / 截图与 OCR），共用同一个 `draft`，一次 Save 提交；字节类字段以 MiB 显示并保留一位小数（`toMiB`），避免 9.5 MiB 在整数输入框里被悄悄取整。`TranscriberSection.tsx` 的端点编辑对话框补 8 个端点级字段（超时 / 分段大小 / 每分钟请求 / 切片并发 / 最多切片数 / 静音阈值 / 最短停顿 / 按静音拆分），此前这些值只能靠改 DB。

**验证**：新增 `backend/tests/017-web-rebuild-and-architecture/test_runtime_limits.py`（18 条，tmp SQLite + `reset_cache()` + 清 12 个相关环境变量）钉住默认值、`_default_payload` 形状、0 = 不限语义、越界夹取、写后立刻生效、部分更新不污染其它字段、env 优先、用户预算不能突破天花板、judge budget < request budget、读库失败回落常量、两道输入闸门。后端全量 **841 passed**。

线上实测（真实后端 + 真实 117 MB / 96.8 分钟媒体）：`POST /api/general/settings` 只带 4 个字段时其余字段不受影响；`llm_max_request_bytes = 10^12` 被夹到 134217728；把 `asr_max_file_mb` 设 1 → 「音频体积 117.7 MB 超过上限 1 MB，请在「设置 → 通用」调高「ASR 最大文件大小」」；设 `asr_max_duration_minutes = 1` → 「音频时长 96.8 分钟超过上限 1 分钟……」。截图 `limits-desktop-general-asr.png` / `limits-desktop-general-llm.png` / `limits-desktop-transcriber-dialog-{top,bottom}.png` / `limits-mobile-*` 人工复核（桌面与 390px 两档）。

闸门：`tsc -b --force` 0 错误、`eslint src` 0 problems、i18n 契约 **427 键**对齐（`i18n-dedupe` duplicates 0 / conflicts 0）、`pnpm build` exit 0（index gzip 160.94 kB）。

踩坑：`settings.transcriber.timeout` / `.chunkSize` / `.maxRpm` 三个键在 `strings.ts:389-392` **早已存在**，我按新语义又加了一遍，直接触发 6 条 TS1117（后写覆盖先写，`i18n-contract` 看不出来因为对象字面量早已折叠）。**加 i18n 键之前先 grep 前缀**，重名一律复用旧键（`chunkConcurrency` 改指既有的 `settings.transcriber.concurrency`）。


### 失败预算可配置化（2026-10-17，第二轮盘点）

上一节把「一次事务能做多大」变成了设置项。这一节处理另一半：**一次失败之后怎么重来**。

#### 问题

这些参数原先全部只能改环境变量，而环境变量要重启后端才生效；界面上完全看不到，
于是「任务失败了 3 次就放弃」「撞上 429 要等一小时」「下载卡住 30 秒才超时」这些行为
对用户来说是不可解释的魔法数字。四组硬编码：

- `backend/app/routers/note.py:169` `NOTE_MAX_RETRIES` / `:170` `NOTE_RETRY_BACKOFF = [5, 15, 45]`
  —— 任务失败后**重跑整条流水线**（重下载、重转写、重调模型）的次数与退避；
- `backend/app/utils/llm_rate_limit.py:235/238/241` `RATE_LIMIT_COOLDOWN_SECONDS` /
  `RATE_LIMIT_MAX_WAIT_SECONDS` / `RATE_LIMIT_RESUME_INTERVAL_SECONDS` —— 429 的冷却窗口、
  累计等待上限、恢复探测间隔；
- `backend/app/downloaders/base.py:18` `YDL_RETRY_OPTS` —— yt-dlp 的 `retries` /
  `fragment_retries` / `socket_timeout`；
- 判定为**不该动**的：`TASK_MAX_WORKERS`（进程级构造期固定，已由 `max_parallel_notes` 覆盖）、
  `NOTE_DISPATCH_WORKERS`（运维逃生口）、媒体保留天数（已有 `media_settings` 表与 `/media` 路由）、
  各类路径（`DATA_DIR` / `NOTE_OUTPUT_DIR` 等）。

#### 决策

1. **新增 7 个字段**，与上一节同样走 `runtime_limits` 门面（5 秒 TTL + 读库失败回落常量 +
   保存即 `reset_cache()`）。范围与默认值：`note_max_retries` 0–10（默认 3）、
   `note_retry_backoff_seconds` 0–300（默认 5.0）、`llm_rate_limit_cooldown_seconds` 0–3600
   （默认 300.0）、`llm_rate_limit_max_wait_seconds` 0–86400（默认 3600.0）、
   `llm_rate_limit_resume_interval_seconds` **10–3600**（默认 300.0）、`download_retries` 0–10
   （默认 3）、`download_socket_timeout_seconds` **5–300**（默认 30）。
2. **环境变量名沿用旧名**（`NOTE_MAX_RETRIES` / `RATE_LIMIT_COOLDOWN_SECONDS` /
   `RATE_LIMIT_MAX_WAIT_SECONDS` / `RATE_LIMIT_RESUME_INTERVAL_SECONDS` / `DOWNLOAD_RETRIES` /
   `DOWNLOAD_SOCKET_TIMEOUT_SECONDS`）。老部署靠这些 env 调参，加了设置项就让它们静默失效
   等于在升级时偷偷改掉生产行为。
3. **`llm_rate_limit_resume_interval_seconds` 越界时夹取而不是回落**：用户填 1 秒表达的意图
   很明确（想尽快恢复），回落成 300 秒等于无视他的选择；但 1 秒一次的探测本身就会把限流
   撞回去，所以抬到下限 10 秒。同理 `download_socket_timeout_seconds` 的 0/负数抬到 5 ——
   yt-dlp 把 `socket_timeout=0` 当成**永不超时**，卡住的连接会永久占住 worker。
4. **`YDL_RETRY_OPTS` 从 dict 改成 `Mapping` 实现**（`backend/app/downloaders/base.py` 的
   `_YdlRetryOpts`）。这不是风格选择：`**` 解包对 dict 子类走 C 快路径直读底层存储，会绕过
   任何 `__getitem__` 重写，所以 dict 子类拿不到「每次解包都重读配置」的效果。读不到运行时
   配置时回落 `_FALLBACK_RETRIES` / `_FALLBACK_SOCKET_TIMEOUT` —— 下载器在测试里常被单独
   加载（`app` 包被桩替换），那时 import `runtime_limits` 会失败。
5. **`note_max_retries` 与 `llm_retry_attempts` 是两层不同的重试**，界面上必须分开说清楚：
   前者重跑整条流水线（分钟级），后者只重试单次 HTTP 请求（秒级）。

#### 消费点

- `backend/app/services/runtime_limits.py`：新增 `note_max_retries()` /
  `note_retry_backoff_seconds()` / `llm_rate_limit_cooldown_seconds()` /
  `llm_rate_limit_max_wait_seconds()` / `llm_rate_limit_resume_interval_seconds()` /
  `download_retries()` / `download_socket_timeout_seconds()`。
- `backend/app/routers/note.py`：`_execute_note_with_retry` 每轮重读次数与退避基数，退避改为
  `delay = backoff_base * (3 ** min(attempt, 2))`（基数 5 → 5/15/45 封顶，与旧行为一致）；
  `_rate_limit_resume_loop` 每次重进循环重读探测间隔。模块常量降级为兜底与文档。
- `backend/app/utils/llm_rate_limit.py`：`note_rate_limit_hit()` 参数为 `None` 时读门面，
  异常回落模块常量。
- `backend/app/downloaders/base.py`：`_YdlRetryOpts`（见决策 4），四个 `**YDL_RETRY_OPTS`
  解包点无需改动。
- 前端 `src/services/general.ts` 扩 7 字段 + 伴生 `_default`/`_limit`/`_min`/`_max`；
  `src/ember/pages/settings/sections/GeneralSection.tsx` 新增第 5 组「失败与重试」
  （`settings.general.group.retry`），7 行共用同一个 draft，一次 Save 提交。

#### 测试与实测

- `backend/tests/017-web-rebuild-and-architecture/test_runtime_limits.py` 新增 8 条（全文件 26 条）：
  默认值来自常量、写后立刻生效、部分更新不影响其它字段、越界夹取、探测间隔抬到下限、
  环境变量仍优先、`dict(**YDL_RETRY_OPTS)` 解包拿到运行时值、`_default_payload()` 形状完整。
- **真实缺陷（回归）**：改完之后 `pytest tests` 出现 5 failed —— `tests/001-bilibili-batch-import/`
  `test_task_retry.py` 的三条用例 `mock.patch.object(note_module, "NOTE_RETRY_BACKOFF", [0,0,0])`、
  `tests/012-rate-limit-backoff/test_rate_limit_backoff.py` 的两条用例
  `monkeypatch.setattr(rl, "RATE_LIMIT_COOLDOWN_SECONDS", 10.0)`，改的都是「已不再被执行路径读取」
  的模块常量。修法是把测试钉到真正被读的那一层：前者改 `mock.patch.object(note_module.runtime_limits,
  "note_max_retries", lambda: 3)` + `note_retry_backoff_seconds -> 0.0`，后者新增
  `_pin_cooldown(monkeypatch, cooldown=..., max_wait=...)` 辅助函数替换 5 处直接 setattr。
  教训：把常量改成门面之后，**任何 mock 该常量的测试都会静默失效**（不报错、只是不再生效），
  必须连测试一起搬。
- 全量后端 `pytest tests -q -p no:cacheprovider` → **859 passed, 2 warnings, 13 subtests passed**。
- 线上实测（重启后端后）：`GET /api/general/settings` 返回 **71 个键**（含 7 个新字段及伴生键）；
  `POST {note_max_retries: 6, llm_rate_limit_cooldown_seconds: 45.0, download_socket_timeout_seconds: 1}`
  → 全部生效且 `max_parallel_notes` 未被动（部分更新语义）；`note_max_retries: 999` → 夹到 10，
  `llm_rate_limit_resume_interval_seconds: 1.0` → 抬到 10.0；`download_socket_timeout_seconds: 1`
  → 抬到 5；门面读到 `note_max_retries=10 / cooldown=45.0 / socket=5 / resume=10.0`，
  `dict(**YDL_RETRY_OPTS)` 同步为 `{'retries': 3, 'fragment_retries': 3, 'socket_timeout': 5}`；
  随后原值回填复原。
- 前端闸门：`i18n-dedupe` duplicates 0 / conflicts 0、`i18n-contract` **442 keys** 两侧对齐、
  `tsc -b --force` 0 errors、`eslint src` 0 problems、`pnpm build` exit 0。
- 截图复核：`scripts/retry-budget-shots.cjs` 拍桌面 1440×900 / 移动 390×844 / 英文 1440×900 三张，
  人工确认第 5 组 7 行齐全（3 / 5 / 300 / 3600 / 300 / 3 / 30）、移动端单列不溢出（`overflowX` 0）、
  英文界面 CJK 计数 0。

### 截图编码与 ffmpeg 超时可配置化（2026-10-17，第三轮盘点）

前两节分别处理了「一次事务能做多大」和「一次失败怎么重来」。这一节补上把两者
连起来的那个量：**一张图有多大**。

#### 问题

用户提「llm 需要标记最大请求体大小（比如只能 30m 的图片之类的）」，落地时发现
只给请求体设上限并不够 —— 请求体是**结果**，决定它的是每张图的字节数：

- `backend/app/utils/video_helper.py` 的 `generate_screenshot()` 写死 `-q:v 2` 且**不缩放**；
  实测 `backend/static/screenshots` 150 张平均 78.2 KB、最大 113.8 KB（1280×410 的源），
  但 4K 视频一张截图就是几百 KB，而 `note.py:1400` 的 `_image_to_data_url()` 是原样
  base64 编码（**不缩放、不重编码**），base64 再涨 1/3；
- `_FFMPEG_TIMEOUT_SECONDS = 60` 连环境变量都没有：网络盘或长视频上超时会让截图
  静默失败（日志一行 error，笔记里就是没有配图）；
- `MAX_JUDGE_CANDIDATES`（200）只认 `OCR_MAX_JUDGE_CANDIDATES` 环境变量，而候选
  时间点列表和图片抢的是**同一份**请求预算。

#### 决策

1. **新增 4 个字段**，与前面同样走 `runtime_limits` 门面（5 秒 TTL + 读库失败回落
   常量 + 保存即 `reset_cache()`）：`screenshot_max_width` 0–7680（**默认 0 = 保持原始
   分辨率**，与历史行为一致，避免老部署截图突然变小）、`screenshot_quality` 1–31
   （默认 2）、`ffmpeg_timeout_seconds` 10–600（默认 60）、`ocr_max_judge_candidates`
   1–1000（默认 200）。
2. **缩放只缩不放**：ffmpeg 滤镜写成 `scale=min(W,iw):-2`，高度 `-2` 保证偶数；宽度为 0
   时**完全不加 `-vf`**，命令行与历史行为逐字节一致。
3. **超时不允许 0**：`subprocess.run(timeout=0)` 会立刻超时，等于让所有截图都失败；
   下限 10 秒是为了挡住「填 1 秒想快点失败」这种手滑。
4. **`video_helper` 用延迟导入 + 兜底**：本模块在测试里常被单独加载（`app` 包被桩
   替换），`from app.services import runtime_limits` 失败时必须仍然按历史参数出图，
   不能因为读不到配置就让截图整条链路挂掉。

#### 实测

- 真实视频（`backend/data/BV1Rch76WEfQ.mp4`）同一时间点：默认 `0/2` → 1280×410、55,061 bytes；
  设 `640/8` → 640×206、9,883 bytes（**5.6 倍**）。
- 线上 API：`GET /api/general/settings` 返回 **85 键**；`POST` 部分更新只改传入字段；
  夹取验证 `99999→7680`、`quality 0→1`、`ffmpeg 0→10`、`candidates 99999→1000`；
  门面读到同一份值；随后原值回填复原。
- 后端全量 **875 passed**；`tsc -b` 0 error；`eslint src` 0 problem；i18n **451 keys** 对齐；
  `pnpm build` exit 0（index-CMbaVHXs.js 517.99 kB gzip 162.38 kB）。
- 截图复核：`C:/Users/Administrator/Downloads/shot-desktop.png`（1440×900）、
  `shot-mobile.png`（390×844，单列不溢出）、`shot-en.png`（英文无 CJK 残留），
  新增第 6 组「截图编码」4 行值与后端默认一致（0 / 2 / 60 / 200）。

#### 三轮盘点后的全量清单

| 轮次 | 字段 | 覆盖的问题 |
| --- | --- | --- |
| 一（11 项） | `asr_max_file_mb` `asr_max_duration_minutes` `asr_silence_split` `asr_silence_noise_db` `asr_min_silence_seconds` `llm_max_request_bytes` `llm_judge_image_budget_bytes` `llm_retry_attempts` `llm_retry_backoff_seconds` `ocr_stage_concurrency` `note_max_images` | 一次事务能做多大 |
| 二（7 项） | `note_max_retries` `note_retry_backoff_seconds` `llm_rate_limit_cooldown_seconds` `llm_rate_limit_max_wait_seconds` `llm_rate_limit_resume_interval_seconds` `download_retries` `download_socket_timeout_seconds` | 一次失败怎么重来 |
| 三（4 项） | `screenshot_max_width` `screenshot_quality` `ffmpeg_timeout_seconds` `ocr_max_judge_candidates` | 一张图有多大 |

判定为**不该动**的（写在这里，免得下次再盘一遍）：`TASK_MAX_WORKERS`（进程级构造期
固定，已由 `max_parallel_notes` 闸门覆盖）、`NOTE_DISPATCH_WORKERS`（运维逃生口）、
媒体保留天数（已有 `media_settings` 表与 `/media` 路由）、`OPENAI_GATEWAY_MAX_REQUEST_BYTES`
（部署侧硬上限，界面调大只会把失败推迟到线上 413）、各类路径类 env，以及
`audio_helper.py` 的 `DEFAULT_COMPRESS_BITRATE`（`compress_audio` 全仓库 0 调用点，已是死代码）。

### 静音参数：端点级覆盖 vs 全局值（2026-10-17，修真实缺陷）

第三轮收尾做端到端串联验证时，抓到一个把「全局静音开关」变成摆设的缺陷。

#### 现象

把通用设置里的 `asr_silence_split` 改成 False、`asr_silence_noise_db` 改成 -42.0、
`asr_min_silence_seconds` 改成 1.25 后，`TranscriberConfigManager().get_active_openai_asr()`
仍然返回 `silence_split=True / -30.0 / 0.5`。也就是说：**通用页那个开关，只对「此后新建的
端点」生效一次，对任何已存在的端点完全无效。**

#### 机制

`backend/app/services/transcriber_config_manager.py` 的 `_normalize_endpoint()` 用
`_global_limits().asr_*()` 补齐三个静音字段的缺省值；而保存路径（`add_openai_asr` /
`update_openai_asr`）会把**补齐后的完整 dict** 写进 `backend/config/transcriber.json`。
于是第一次保存那一刻的全局值被冻结成端点显式值，之后改全局永远读不到——
`_as_bool(raw.get("silence_split"), global)` 里的 `raw.get(...)` 从此永远有值。
#### 修法：键不存在 = 跟随全局

1. `_SILENCE_FIELDS = ("silence_split", "silence_noise_db", "min_silence_seconds")`，
   端点新增 `explicit_fields` 账本：只有记在里面的字段才采用存储值，其余一律实时回落
   全局（因此改通用页立刻影响所有跟随的端点）。
2. `_persistable(endpoint)` 在**写盘前**把未显式指定的静音字段摘掉——「跟随全局」必须在
   文件里表现为键不存在，否则下次读取又会被当成显式值。
3. `add_openai_asr` 的三个静音参数默认值改为 `None`；路由层不再替用户填 -30.0 / 0.5 / True，
   改成原样透传（不传 = 不落盘）。
4. `update_openai_asr` 传 `null` = **撤销覆盖**、回到跟随全局；路由改用
   `**data.model_dump(exclude_unset=True)`，让「请求里没出现这个键」与「显式传 null」
   成为两件不同的事（前者不动，后者撤销）。
5. **历史配置**没有 `explicit_fields`，三个字段一律视为未指定——端点对话框直到本轮才第一次
   出现这些控件，老值必然是 `_normalize_endpoint` 自动填的默认值，不是用户选择。

#### 前端

`src/ember/pages/settings/sections/TranscriberSection.tsx` 的端点对话框新增
「静音参数跟随通用设置」开关：打开时三个控件置灰、不落盘，并显示当前全局值
（形如「当前全局：噪声门限 -30 dB / 最短静音 0.5 秒 / 静音拆分 开」）；关掉才把当前值
固定到该端点。初始状态由 `endpoint.explicit_fields` 推导，所以老端点打开就是「跟随」。
#### 验证

- 新增 `backend/tests/017-web-rebuild-and-architecture/test_transcriber_silence_follow_global.py`
  5 条：全局改动影响未显式指定的端点、显式覆盖优先、`null` 撤销覆盖、继承值不落盘、
  历史配置（有值无标记）跟随全局且写回时清理。
- 后端全量 **880 passed**。
- 线上 API 串联实测（真实端点）：`explicit []` → 改全局 `-42.0/1.25/False` → 端点读到
  `-42.0/1.25/False`；显式覆盖 `silence_split=true` → `explicit ['silence_split']`，再改全局
  仍为 True；传 `null` → `explicit []`、立刻跟随全局；最后原值回填，端点恢复
  `True / -30.0 / 0.5`。
- 浏览器实测：对话框内「跟随」开 → 2 个数字框与拆分开关全部 disabled、显示全局值；
  关掉 → 全部解禁（探针 `scripts/probe-follow-toggle.cjs`）。截图
  `C:/Users/Administrator/Downloads/silence-follow-zh.png`（1440×900）、
  `silence-follow-en.png`、`silence-follow-mobile.png`（390×844）均人工复核。

### 浏览器扩展 Platform 收窄到 bilibili-only（2026-10-18）

决策：扩展端 `Platform` 类型收窄为 `'bilibili'`，`detectPlatform` 只认 `bilibili.com/video/`
与 `b23.tv/`；`COOKIE_DOMAINS` 与 `SUPPORTED_COOKIE_PLATFORMS` 只剩 bilibili；右键菜单
`documentUrlPatterns` 只剩这两个域；`PlatformBadge` 颜色表与 `SITE_SUFFIX_RE` 同步收窄；
不支持提示改为「目前只支持哔哩哔哩 Bilibili」。

理由：后端生成链路已只保留 Bilibili downloader（`SUPPORT_PLATFORM_MAP`），扩展若继续
列出 YouTube / 抖音 / 快手，用户会看到平台徽章、点下按钮，然后拿到后端 400。

验证：`pnpm typecheck` 退出码 0、`pnpm exec vitest run test` 2 passed、`pnpm build` 退出码 0。

### 笔记生成 prompt 重塑：第一人称 / 补充内容 / 图内保留（2026-10-18）

#### 问题

用户反馈生成结果对课程内容保留不好：笔记读起来像第三方摘要（「上一节课回顾了……」），
不是讲课人自己的讲义；课内没展开的地方要么缺失、要么与课内内容混在一起无法分辨；
学术类课程里板书/课件上的练习题、公式推导、图示内容丢失严重。

#### 决策

1. **叙述人称是恒定约束**，写在 `BASE_PROMPT`，对所有场景生效：全篇讲课人第一人称
   （「我」讲自己的判断与取舍，「我们」带着听众一起想），字幕口语转书面语（删口头填充、
   合断句，但不改口径与结论），禁止「视频中提到 / 作者介绍了 / 老师讲到」这类第三人称转述。
2. **补充内容用唯一标记** `> 补充：`（Markdown 引用块）：每条补充独立成段、以该前缀开头、
   跟在被解释段落之后；课内讲过的内容绝不能用这个标记。补充只允许讲解性展开（补推导、
   补例子、补直觉），不得编造课上没有的事实性断言，拿不准写「视频未说明」。补多少由模型
   按内容难度决定，不设硬上限。
3. **学术场景**（`SCENE_PROMPTS["academic"]`）显式要求：知识点成条（定义 / 成立条件 /
   适用范围分开写）、公式推导逐步写（每步写依据）、练习题完整保留（题干 / 已知 / 选项 /
   答案 / 步骤 / 结果）、通俗讲解与严谨表述并存、图内内容优先保留（板书 / 课件 / 图表 /
   批注 / 坐标轴标注按图写，表格转 Markdown 表格）。
4. 三个场景与两个详略档位全部扩写；`get_toc_format()` 明确目录只含 `##` 级标题且与正文
   逐字一致；`get_summary_format()` 固定二级标题 `## AI 总结` 且不引入正文外内容；
   `MERGE_PROMPT` 要求原样保留 `> 补充：` 段落并保持第一人称。

#### 约束（测试锁定）

`backend/tests/015-note-preset-scene-and-detail/test_first_person_and_supplement_contract.py`
共 12 条：第一人称与禁止第三人称、`> 补充：` 标记存在且唯一、补充的边界（不得编造）、
图内内容优先、每个场景都带第一人称与标记、学术场景五个保留项、合并提示词保留补充段。

#### 真实生成验证（同一视频、同一模型、同一参数，只换提示词）

视频 `https://www.bilibili.com/video/BV1Rch76WEfQ`（NJU 软件工程「需求和架构 (1)」，522 段字幕），
模型 `gpt-6-luna-codex`，`scene=academic`、`detail=detailed`、`format=[toc,link,summary]`、`screenshot=false`。

| 指标 | 旧提示词 | 新提示词（最终） |
| --- | --- | --- |
| 全文「我」/「我们」 | 0 / 0 | 60 / 33 |
| `> 补充：` 段落 | 0 | 3 |
| 目录形态 | 9 条锚点链接 | 12 条无序列表，与正文章节逐字一致 |
| 第三人称转述（视频中 / 作者介绍 / 老师讲） | 0 | 1（「视频中提出的 Pyxrc」，局部指代，非叙述视角） |

补充段落样例（跟在被解释段落之后，与课内内容可区分）：

- 「补充：验收场景把需求转成可观察的条件。例如，"保存教材记录后重新打开页面，数据仍然存在"就比"系统应支持教材管理"更容易验证。」
- 「补充：中间表示把"要做什么"和"如何在某个平台实现"分开。」

#### 真实生成暴露的两个缺陷（已修）

1. **改完 `prompt.py` 必须重启后端**：`BASE_PROMPT` 是模块级常量，进程内不会重新读文件。
   第一次真实生成拿到的仍是旧文案（0 个「我」、0 条补充），重启后同一请求立刻变成 60 个「我」、
   3 条补充。后续所有提示词实验都以「重启后端」为前提。
2. **目录被写成标题骨架**：`get_toc_format()` 原话「生成一个只含 `##` 级标题的目录」被模型理解成
   「把所有标题原样抄一遍」，产出 `## 目录` + 12 行裸标题，正文再重复一次。改成「`## 目录` 小节 +
   无序列表 `- 章节标题`，标题逐字一致、不带时间标记、目录里不写正文」后，目录恢复为 12 条列表。

#### 前端：时间标记不再裸露在标题里

提示词要求每个 `##` 标题后跟 `*Content-[mm:ss]`，原样渲染时标题读作
「需求永远无法一次说清：变化如何累积成技术债 *Content-[32:35]」。
`src/ember/features/reader/MarkdownNote.tsx` 新增 `humanizeTimeMarks()`：
`*Content-[mm:ss]` → 行内代码 `mm:ss`，`*Screenshot-[mm:ss]` → 行内代码 `截图 mm:ss`，
在 `useMemo` 里先过一遍再交给 react-markdown。

#### 验证

- `pytest tests/015-note-preset-scene-and-detail -q` → 54 passed（原 40 + 新增 14）。
- 后端全量 `pytest tests -q` → 894 passed（含本轮新增 14 条）。
- `BASE_PROMPT` 仍只有 `{video_title}` / `{tags}` / `{segment_text}` 三个占位符，`format()` 不抛
  KeyError；`tests/008-ocr-assist-and-legacy-cleanup` 的「OCR 为空时提示词里不出现参考块」仍然成立
  （新文案把「画面文字参考（OCR）」改述为「画面文字」的 OCR 参考，避免与那个标题同名）。
- 前端 `pnpm exec tsc -b --force` 0 error、`npx eslint src` 0 problem、`pnpm build` 退出码 0
  （`dist/assets/index-gtQjKyUi.js` 519.15 kB / gzip 162.74 kB）。
- 三视口截图 `C:/Users/Administrator/Downloads/prompt-desktop.png`（1440×900）、`prompt-tablet.png`
  （834×1112）、`prompt-mobile.png`（390×844）：目录为列表、3 条补充为带左侧强调线的引用块、
  标题里的时间戳渲染为行内代码、`*Content-[` 原文不再出现、横向溢出 0。

### 截图链路：缓存命中也要把视频找回来（2026-10-18）

- 缺陷：第二次生成（音频缓存命中）时 `_download_media` 直接返回缓存对象，而 `self.video_path`
  只在真正下载的分支里赋值；`_post_process_markdown` 的插图分支以 `self.video_path` 为开关，
  于是整步静默跳过 —— 正文里留下 31 个 `[[SHOT-n]]` 占位符、0 张图，日志里一切正常（任务
  `1d994afa-a36c-4861-b4b9-f83d7d5beb12`）。
- 修法：`_adopt_video_path()`（backend/app/services/note.py）在缓存命中且 `need_video` 时按三级顺序
  找回视频：缓存里记的 `video_path` → `<output_dir>/<video_id>.mp4` → 重新 `download_video()`
  （命中已存在文件不会重复下载）；都找不到就记 warning，不再假装一切正常。
- 兜底：`_post_process_markdown` 结尾用 `_SHOT_MARKER_ANY` 清掉残留占位符并记 warning ——
  「这里本该有图」的空壳比没有图更糟。
- 测试：backend/tests/017-web-rebuild-and-architecture/test_screenshot_pipeline.py 共 8 条（缓存命中
  恢复路径、缓存路径失效时重新下载、不需要视频时不动下载器、单帧渲染幂等、复用已渲染帧、
  视频缺失时清占位符并记日志、模型多写编号时清理、无判定帧时为空）。
- 真实复验（任务 `3b7ff35d`，`screenshot=true`、`video_interval=180`、`max_frames=6`，音频走缓存）：
  markdown 10,434 字符，`![` 30 处、`/static/screenshots/` 30 处、`[[SHOT` 残留 0。

### 站内锚点：目录与大纲不再新开页面（2026-10-18）

- 缺陷：`MarkdownNote` 的 `a` 渲染器给所有链接加了 `target="_blank"`，笔记目录里的
  `[标题](#锚点)` 因此新开一个标签页；左侧大纲用 `<a href="#id">` 改 hash，在 HashRouter
  （桌面端）下会被当成路由跳转，直接把读者带离笔记。
- 修法：新建 `src/ember/features/reader/anchors.ts` 的 `scrollToAnchor()` —— 先按 id 找，找不到
  再按标题文本归一化匹配（标题 id 由 rehype-slug 生成、大纲 id 由 outline.ts 的 slugify 生成、
  模型写的锚点又是第三种写法，不能赌三者相等）。`MarkdownNote` 的 `a` 渲染器对 `#` 开头的链接
  改为 preventDefault + 平滑滚动（`prefers-reduced-motion` 时用 `auto`），外部链接仍
  `target="_blank"`；`NotePanel` 的大纲项由 `<a>` 改为 `<button>`；标题加 `scroll-mt-24`
  抵消吸顶头部。
- 验证：`BillNote_frontend/scripts/probe-anchors2.cjs`（Playwright 路由拦截注入含锚点的 markdown）
  站内链接点击后 URL 不变、scrollY 0 → 3987、目标标题 top=96px；外部链接仍 `target="_blank"`
  且真的弹出新页面。`scripts/probe-anchors.cjs` 大纲第 4 项点击后 scrollY 0 → 2417、URL 不变、
  无 popup、无 pageerror。