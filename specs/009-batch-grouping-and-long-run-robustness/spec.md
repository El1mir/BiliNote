# 009 · 批量分组与长批量健壮性

- **状态**：implemented
- **日期**：2026-10-05
- **范围**：批量导入的任务归属（每次批量一个新建组）、一次提交 200 个长视频时的并发/重启/磁盘/失败放大问题、批量状态轮询
- **上游**：001（批量导入与并发隔离）、005（任务阶段进度）、006（流水线性能）、007（媒体缓存治理）

## 1. 背景

用户实测反馈四件事，其中两件属于本 spec：

**（一）批量任务落到「未分组」。** 现状有两条独立成因：

1. 后端 `_resolve_batch_group`（`backend/app/routers/note.py:467-487`）在组名为空时直接 `return ""`，整批落进 `group_id IS NULL` 的虚拟「未分组」区；`create_group` 抛错时也只 warning 后退化为未分组。
2. 前端 `BatchImportDialog`（`BillNote_frontend/src/pages/HomePage/components/BatchImportDialog.tsx:91-132`）默认拿 `/expand` 返回的 `result.title` 当组名，抓不到标题时就是空串；且提交后 `addPendingTask`（`BillNote_frontend/src/store/taskStore/index.ts:294-302`）只写 `groupName` 不写 `groupId`，而 `NoteHistory.tsx:85-90` 要求两者同时存在，于是刚提交的任务会先显示成「未分组」，要等下一次 `loadTasks` 才跳回正确的组。

另有 `MAX_GROUPS = 200`（`backend/app/db/note_group_dao.py:36`）与「每次批量新建一个组」直接冲突：第 201 次批量会静默退化回未分组。

**（二）一次生成 200 个长视频会崩。** 只读审计确认的关键机制：

- **批量内实际并发度 = 1，与 `TASK_MAX_WORKERS` 和并行闸门无关。** `backend/app/routers/note.py:831-853` 用 `background_tasks.add_task(run_note_task, ...)` 逐条挂后台任务，而 Starlette 的 `BackgroundTasks.__call__` 是 `for task in self.tasks: await task()` —— 严格串行。200 个任务在一个 anyio 线程上排队跑完，`_ParallelGate`（`note.py:148-200`）与 `task_serial_executor` 在单次批量请求内根本不被争用。叠加 `DEFAULT_MAX_PARALLEL_NOTES = 1`（`backend/app/db/models/general_settings.py:12`）与 1–3 小时视频每任务 10–60 分钟的实际耗时，**200 个任务是 1.5–8 天量级**。
- **重启即全丢。** 队列无持久化、无重启恢复（全仓 `resume|requeue|recover` 零命中）。重启后 PENDING/TRANSCRIBING 任务永久僵死，且因 `_IN_FLIGHT_STATUSES` 含 PENDING（`note.py:234-242`），这些视频**连重新提交都被拒**。实测现场：清理前 195 条任务的状态文件全部停在 PENDING。
- **磁盘耗尽。** 下载的音视频成功后不删除（`backend/app/services/note.py:1666-1691` 只登记），全部落在同一个扁平目录 `backend/data/data`（`backend/app/utils/path_helper.py:8-18`），只靠每小时上限 200 条、默认 3 天保留的 `media_cleanup_loop`（`backend/app/services/media_resource_service.py:292-303`）回收。200 × 1–3 h 的 mp3 约 6–18 GB，开截图/视频理解则达数百 GB。
- **重试风暴 ×4 成本。** `NOTE_MAX_RETRIES = 3` + `NOTE_RETRY_BACKOFF = [5, 15, 45]`（`note.py:126-128`、`note.py:340-368`）每次重试**重跑整条流水线**（重下载、重转写、重总结）。系统性故障（cookie 失效、供应商宕机、413）会命中全部 200 个任务。
- **前端先崩。** `BillNote_frontend/src/hooks/useTaskPolling.ts:86-90` 是 N+1 串行轮询：200 个待办任务每 3 秒发 200 个顺序 `GET /task_status`（≈67 req/s），且成功响应每次都重发整份 markdown+transcript（`note.py:1036-1049`）；叠加 `GET /task_list` 每次调用做 400 次 JSON 读+解析（`note.py:1175-1176`）与单进程 uvicorn（`backend/main.py:125-129`），30s axios 超时（`BillNote_frontend/src/utils/request.ts:29`）触发后 `MAX_POLL_FAILURES = 5`（`useTaskPolling.ts:67,129-132`）会把**还在跑**的任务在客户端误标 FAILED —— 正是代码注释里警告过的「误标失败 + 重复提交」。

其余已确认的技术缺陷：全仓无 WAL / `busy_timeout` / PRAGMA（`backend/app/db/engine.py` 全文已读）；`video_tasks` 无 `(video_id, platform)` 索引，去重探测全表扫；`_ParallelGate.reconfigure` 扩容时替换 `BoundedSemaphore` 对象（`note.py:169-172`）会遗弃已阻塞线程，`release_excess()`（`note.py:185-192`）**零调用点**；`backend/app/downloaders/bilibili_downloader.py:47` 用 `delete=False` 建 NetScape cookie 临时文件且全仓无删除点（含 live SESSDATA，每任务泄漏一个）；`shutil.disk_usage` 全仓零命中。

## 2. 目标

1. 每次批量提交都落到**一个新建的组**，不再出现「批量任务被解析到未分组」。
2. 批量提交后，任务在前端**立即**出现在正确的组里，不等下一次 `loadTasks`。
3. 单次批量 200 个长视频时，批量内真正并发执行（吃满用户设定的并行数），而不是串行跑完。
4. 进程重启后，被中断的在途任务自动恢复执行，且不丢失当初的生成参数。
5. 长批量运行期间磁盘不会无限增长；磁盘真的不够时拒绝新任务，而不是跑到一半以 IO 错误失败。
6. 系统性故障不会让 200 个任务各重跑 4 遍完整流水线。
7. 200 个待办任务时前端轮询不再打爆后端，也不会把在跑的任务误标为失败。
8. 需求④的「缓存边界」（按总量清理，不等过期）落地；该部分按 `specs/README.md:25` 修订 007，见 §8。

## 3. 非目标

- 不引入 Redis / Celery 等任务队列中间件（沿用 001 §23 的决策）。
- 不承诺长任务的断点续跑：重启后恢复的任务**从头重跑**（下载与转写均无中间断点）。
- 不清理 `note_results/` 下的笔记 Markdown/JSON 与 `backend/models/` 的 whisper 模型（沿用 007 §3）。
- 不为批量设置硬性条数上限。
- 不改动单条提交（`POST /generate_note`）的归属语义：单条任务仍落「未分组」。

## 4. 已定决策

| # | 决策 | 结论 |
| --- | --- | --- |
| 1 | 批量组名来源 | 前端组名输入框改**必填**，清空不让提交；不做后端自动生成时间戳兜底 |
| 2 | 建组时机 | **延后建组**：先把整批过完去重/在途判定，只有确实至少一条真正入队时才 `create_group`；全被跳过则不产生空组 |
| 3 | 建组失败 | `MAX_GROUPS` 200 → **1000**；建组失败（含超限）**明确报错**，不再静默退化为未分组 |
| 4 | 前端归属显示 | 用 `/generate_notes` 响应里的 `group_id` 直接写进本地任务，不依赖后续 `loadTasks` 修正 |
| 5 | 单条任务 | 保持落「未分组」 |
| 6 | 并发机制 | 批量入口不再逐条挂 `background_tasks.add_task`；改为受闸门约束的调度器，**闸门在池外**（先 `acquire` 再提交线程池，完成时归还），批量内真并发 |
| 7 | 默认并发 | `DEFAULT_MAX_PARALLEL_NOTES` 1 → 3；上限保持 8 |
| 8 | 重启恢复 | `video_tasks` 新增 `payload_json` 列存提交时的完整生成参数；启动时扫描**在途状态**自动重入队 |
| 9 | 中断范围 | 只重入队 PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/FORMATTING/SAVING；**FAILED 不动**（要重跑由用户手动点） |
| 10 | 重入队错峰 | 不另做启动专用节流：全部交给同一个闸门调度，并发由 `max_parallel_notes` 统一控制 |
| 11 | 磁盘门禁 | 新增 `shutil.disk_usage` 检查；剩余空间 < 阈值（默认 5 GB）时拒绝新的生成提交并返回明确错误码 |
| 12 | 失败熔断 | 单任务仍重试 3 次；新增「连续 N 个任务失败则暂停整批」的熔断 |
| 13 | 批量条数 | 不设硬上限；前端超过 200 条时二次确认并提示预估磁盘与时长 |
| 14 | 前端轮询 | 新增批量状态端点（一次拿回全部待办），轮询改为单次调用；`get_task_status` 成功时不再每次重发整份 markdown+transcript |
| 15 | 批量状态端点方法 | 用 `POST`（200 个 task_id 拼进 GET query 会超长） |
| 16 | 落档 | 需求②③进本 spec；需求④（缓存边界）按 `specs/README.md:25` 修订 007 |

## 5. 接口草案

- `POST /api/task_status/batch`：请求 `{task_ids: string[]}`，返回每个 id 的**轻量**状态（`status/stage/stage_label/progress/stage_progress/message/updated_at`），**不含** markdown 与 transcript；未知 id 返回 `null` 而不是报错。
- `GET /api/general/settings` 与 `POST /api/general/settings` 扩展字段（需求④）：`cache_limit_bytes`（默认 10 GiB，`0` = 不限）、`min_free_disk_bytes`（默认 5 GiB）。
- `POST /api/generate_notes` 的失败语义补充：磁盘不足与建组失败都返回明确错误码（沿用 007/001 的 `R.error(code=...)` 约定；注意 `ResponseWrapper.error` 的 HTTP 层仍是 200，错误码在 body 的 `code` 字段 —— 见 `backend/tests/007-note-archive-and-media-cache/test_note_group_api.py:15-17`）。

## 6. 验收

- 连续两次批量提交得到**两个不同的组**，各自的成员正确；不再出现落到未分组的情况。
- 组名输入框为空时无法提交；提交后任务立刻出现在正确的组里。
- 批量提交全部条目都被去重/在途跳过时，**不产生空组**。
- 组数达到上限时批量提交明确报错，而不是静默落未分组。
- 单次批量 200 条时，同时执行的任务数受 `max_parallel_notes` 约束（默认 3），而不是串行 1 个。
- 并发数运行期可调：调大后新任务立刻按新并发执行；调小后不会永久吞掉名额。
- 重启后，此前处于在途状态的任务自动重新开始执行，且使用**当初提交的参数**（quality / model / provider / screenshot 等）；FAILED 的任务不被自动重跑。
- 磁盘剩余低于阈值时，新的生成提交被拒绝并给出可读提示。
- 连续多个任务因同类错误失败时，整批暂停而不是让全部任务各重跑 4 遍。
- 200 个待办任务时前端每轮轮询只发 1 个状态请求；仍在运行的任务不会被客户端误标为失败。
- 需求④：总字节超上限时，按最旧优先删到阈值以下；活跃/重试中的任务资源不被删除；SUCCESS 与 FAILED 都算「已完成」；`0` 表示不限。
- 后端测试、前端测试、生产构建通过；spec tickets 与实现状态同步。

## 7. 实现清单

| # | 工单 | 状态 |
| --- | --- | --- |
| 01 | 批量分组：上限与报错、延后建组、前端必填与归属 | 已完成 |
| 02 | 真并发调度器与闸门修复、默认并发 3 | 已完成 |
| 03 | 重启恢复：`payload_json` 列、迁移与启动重入队 | 已完成 |
| 04 | 磁盘门禁与连续失败熔断 | 已完成 |
| 05 | SQLite WAL/busy_timeout、`video_tasks` 索引、cookie 文件泄漏 | 已完成 |
| 06 | 前端批量状态端点与轮询改造、批量 >200 二次确认 | 已完成 |
| 07 | 缓存边界（需求④，修订 007）与通用设置 UI | 已完成 |
| 08 | 测试与回归网 | 已完成 |

## 8. 与 007 的关系

需求④「通用设置内加入缓存边界」按 `specs/README.md:25` 的规则**修订 007**（007 本就是「媒体缓存治理」spec，但只覆盖时间维度），在 007 spec 内以带日期的修订章节记录，并在其实现清单追加工单。本 spec 不重复该设计，只在 §7 保留一条指向它的工单。

## 9. 待确认问题

无。范围与关键策略已由用户逐轮确认（2026-10-05）。

## 10. 验证记录（2026-10-05 收尾）

### 10.1 自动化门禁

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` | **572 passed, 2 warnings, 13 subtests passed**（exit 0） |
| 前端类型 | `cd BillNote_frontend; pnpm exec tsc -p tsconfig.app.json --noEmit` | 110 errors（HEAD 基线 192，净减 82） |
| 前端单测 | `pnpm test` | 4 files / 21 tests passed |
| 前端构建 | `pnpm build` | `✓ built in 1m 2s`，exit 0 |

唯一稳定 warning 是 `tests/006-note-pipeline-performance/test_downloader_skip_download.py::DownloaderInterfaceTest::test_every_platform_accepts_skip_download` 的 `<unknown>:124: DeprecationWarning: invalid escape sequence '\('`，属既有、与本 spec 无关。

> **前端类型门禁的坑（收尾时发现）**：`pnpm exec tsc --noEmit` 在本仓库**什么都没检查**。根 `BillNote_frontend/tsconfig.json` 是 solution 式配置（`"files": []` + 只列 `references`），不传 `-b`/`-p` 时 TypeScript 只解析这个空文件集，于是恒 exit 0、零输出 —— 之前记录的「exit 0 零输出」是假绿。真正的类型检查是 `tsc -p tsconfig.app.json`（`include: ["src"]`、`strict` + `noUnusedLocals` + `noUnusedParameters`），当前 **110 errors**。用 `git stash push -- BillNote_frontend` 量到的 HEAD 基线是 **192 errors**，即本次改动**净减 82**：`NoteForm.tsx` 46 → 0、`MarkdownHeader.tsx` 10 → 0、`NoteHistory.tsx` 7 → 0、`useTaskPolling.ts` 3 → 0、`services/note.ts` 4 → 0、`store/taskStore/index.ts` 4 → 0、`MarkdownViewer.tsx` 19 → 10；唯一上升的是 `store/providerStore/index.ts` 11 → 13（该文件本 spec 未改，属既有波动）。110 条**全部落在本次未触碰或仅做删减的文件**里，`pnpm build`（vite，不做类型检查）仍 exit 0。

### 10.2 新增测试文件

`backend/tests/009-batch-grouping-and-long-run-robustness/` 下 11 个文件：`test_batch_grouping.py`(5)、`test_parallel_gate.py`(7)、`test_parallel_scheduler.py`(4)、`test_startup_requeue.py`(9)、`test_disk_gate_and_circuit_breaker.py`(15)、`test_task_status_batch.py`(13)、`test_sqlite_pragma.py`(7)、`test_video_task_index.py`(6)、`test_cookie_temp_cleanup.py`(6)、`test_cache_limit_cleanup.py`(4)、`test_general_settings_cache_fields.py`(23)。

另补强 `backend/tests/001-bilibili-batch-import/test_batch_generate_api.py`（3 → 9 用例，覆盖 `group_name` 建组路径、延后建组、建组失败报错、`payload_json` 落库、磁盘门禁），并修正 `backend/tests/007-note-archive-and-media-cache/test_note_group_api.py` 对 `MAX_GROUPS` 的期望（200 → 1000）。

### 10.3 真实环境冒烟（实跑 `backend/main.py`，端口 8483）

- `GET /api/sys_health` → `{"backend":"ok","ffmpeg":"ok","db":"ok",...}`。
- `GET /api/general/settings` → 11 个键齐备（`max_parallel_notes` 及其 `_limit`、`cache_limit_bytes=10737418240`、`min_free_disk_bytes=5368709120`、`circuit_breaker_threshold=5` 及各自 `_default`/`_limit`）。
- `GET /api/media/cache/limit` → `code=0`。
- `POST /api/task_status/batch {"task_ids":["nope-1"]}` → `{"states":{"nope-1":null}}`（未知 id 返回 null，符合 §5）。
- 启动日志：`task_recovery - 启动恢复：没有需要在途任务（扫描 0 条）`（库已清空）；`Media cleanup completed: ... deleted=0`；`容量边界未超限: total=60263495 limit=10737418240 entries=6`。
- schema 实查：`general_settings` 列为 `id/max_parallel_notes/cache_limit_bytes/min_free_disk_bytes/circuit_breaker_threshold`；`video_tasks` 列为 `id/video_id/platform/task_id/created_at/group_id/payload_json`，索引含 `ix_video_tasks_video_platform`。

### 10.4 已知遗留

- `backend/app/services/media_resource_service.py` 的 `Column[...]` 静态推断告警**已全部消除**（pyright 19 → 0）。做法是按仓库既有约定改写，而不是加抑制注释：新增 `_row_value(row, name)`（属性名是变量时 `getattr` 结果为 `Any`，不再把 `Column[...]` 带进下游比较/算术）与 `_mark_row_failed(row, message)`（`setattr` 而非直接赋值），与 `backend/app/db/general_settings_dao.py` 的写法一致。
  **教训**：`# pi-lens-ignore: Pyright:reportXXX` 注释**不能**抑制 pyright —— 这些是真实报错，必须改代码。另：本仓库 `.venv` 内没有 pyright，`lens_diagnostics mode=full` 对该文件反复返回 `LSP sweep: 0 file(s) confirmed`，唯一可靠的地面真值是 `npx --yes pyright@latest <file>`（对照基线：`git show HEAD:<path>` 写到**仓库内**临时文件再跑，放 `$env:TEMP` 会多出 `reportMissingImports` 噪音）。
  其余文件的 pyright 计数均**低于或持平** HEAD 基线（`backend/app/routers/note.py` 13 vs 33、`backend/app/downloaders/bilibili_downloader.py` 18 vs 29、`backend/app/utils/video_reader.py` 5 vs 5）。
- `backend/app/routers/note.py` 的既有 pyright 噪声（`model_name: str = None`、`grid_size=[]` 可变默认参数、`getattr(...) is True`）为改动前既有，未扩大。
- 批量轮询（`BillNote_frontend/src/hooks/useTaskPolling.ts`）无前端自动化测试 —— 项目 `tests/` 下无该 hook 的测试基建，验收靠代码审查 + 上述 `tsc`/`build` 门禁。
- 「当前缓存占用」未在通用设置页展示：后端目前只有 `preview_cache_limit()`（`GET /api/media/cache/limit`）这一个观测入口，尚未接出实时读数。
