# 011 · 失败任务批量重试

- **状态**：implemented
- **日期**：2026-10-05
- **范围**：`backend/app/services/task_retry.py`（新）、`backend/app/routers/note.py`（追加 `POST /retry_failed_tasks`）、`BillNote_frontend/src/services/note.ts`、`BillNote_frontend/src/pages/HomePage/components/History.tsx`、`backend/tests/011-failed-task-retry/`
- **上游**：[009-batch-grouping-and-long-run-robustness](../009-batch-grouping-and-long-run-robustness/spec.md)（`payload_json` 列、`_dispatch_note_task`、熔断与磁盘门禁）、[006-note-pipeline-performance](../006-note-pipeline-performance/spec.md)（`_execute_note_with_retry` 任务级自动重试）

## 1. 背景

任务失败之后没有出口：只能重新走一遍生成表单 —— 重新找那个视频、重新选一次参数。这个代价在批量导入时被放大得很厉害：一次导入 200 条长视频，挂了 30 条，就得手工重来 30 次，而这些任务的参数其实**在创建时就完整存下来了**（spec 009 加的 `video_tasks.payload_json`）。

同时，启动恢复（`backend/app/services/task_recovery.py`）**故意不碰 FAILED**：

> FAILED 是已经有结论的任务，重启后自己活过来会让用户莫名其妙。

这个取舍是对的，但它意味着「已经失败」的任务在系统里没有任何自动出口 —— 必须由**用户显式发起**。本规格补的就是这条路。

用户需求原文（m02871）：

> 能不能全选数据库内者失败的任务（）或者是某个组内失败的任务重做，就是还是全选分组，但是加个按钮能自动重试失败的任务

## 2. 目标

1. 一次请求把「当前可见范围」（某个组 / 未分组 / 全部）内的**失败任务**全部重新排队。
2. **原地重试**：复用同一个 `task_id` 与分组归属，列表里那条记录从「失败」变回「排队中」，历史不因此多出一条。用户要的是「那条失败的再跑一遍」，不是「列表里多出一条」。
3. 参数**沿用创建时的 `payload_json`**，而不是回落到默认值。
4. 与既有门禁一致：转写模型未就绪、磁盘不足时拒绝整批；用户主动重试 = 熔断复位信号。
5. **如实汇报**：哪些重试了、哪些跳过了（带原因）、哪些在库里已不存在 —— 静默跳过等于让用户以为全都重试了。

## 3. 非目标

1. **不做任务级自动重试的调整**。`backend/app/routers/note.py:599` 的 `_execute_note_with_retry`（`NOTE_MAX_RETRIES` 默认 3）是流水线内部的重试，与本规格的「用户手动重试」是两层，互不影响。
2. **不重试 SUCCESS**。已经有笔记了，重跑只会覆盖用户已经看过的东西；想再生成一次应该走正常提交入口（那边有「已生成」去重提示）。本规格**不**提供「强制重新生成」。
3. **不重试在途任务**。它还在跑，重试等于把同一个 `task_id` 跑两遍，两个线程写同一份文件。
4. **不建新组、不动分组归属**。重试沿用原分组（决策 2）。
5. **不改前端列表的状态展示**。重试后那条记录回到「排队中」，由既有轮询机制接管。

## 4. 设计

### 4.1 模块位置与职责边界

新建 `backend/app/services/task_retry.py`。它与 `backend/app/services/task_recovery.py` 共用同一套「从 DB 行还原 `run_note_task` 参数」的逻辑（都按 `PAYLOAD_KEYS` 白名单重建），但**判定方向相反**：

| | 触发者 | 碰什么状态 | 状态文件读不到时 |
| --- | --- | --- | --- |
| `task_recovery.py` | 服务启动 | 只碰**在途** | 视为**可恢复** |
| `task_retry.py` | 用户显式发起 | 只碰 **FAILED** | 视为**不重试** |

「状态文件读不到」两边取舍相反，是刻意的：启动恢复时进程在写第一次状态前就被杀了，读不到恰恰最该救；而用户手动重试时进程活得好好的，读不到只说明这个任务从没真正开始过，重试它没有依据。

`_fallback_payload()`（`payload_json` 缺失时按 `video_id` 重建 bilibili URL）在两个模块里**各有一份**，不做跨模块复用：恢复要尽量救活、重试要尽量不误导，两个降级策略会各自演化，强行共用一个函数会让任意一边改不动。

### 4.2 「什么算失败」判定在服务端

`_select_retryable(rows)` 读 `<task_id>.status.json`（状态**活在文件里**，`video_tasks` 表的 status 列从不更新），三分类：

- `FAILED` → 可重试。
- 在途（`PENDING`/`PARSING`/`DOWNLOADING`/`TRANSCRIBING`/`SUMMARIZING`/`FORMATTING`/`SAVING`）→ 跳过，原因「任务仍在执行」。
- 读不到 → 跳过，原因「任务尚未开始，没有可重试的失败记录」。
- 其它（`SUCCESS` 及任何将来新增的未知状态）→ 跳过，原因「任务状态为 {status}，无需重试」。**不猜。**

### 4.3 端点契约

```http
POST /api/retry_failed_tasks
{ "scope": "all" | "group", "group_id": "..." | null }
```

返回 `{"scope", "group_id", "candidates", "requeued", "skipped", "missing"}`：

- `candidates`：范围内扫到的任务条数（**不是**失败任务条数）。
- `requeued`：成功重新入队的 `task_id` 列表。
- `skipped`：`{task_id, reason}` 列表。
- `missing`：分组里列出来、但库里已不存在的 `task_id`。

`scope: "group"` + `group_id: null` = **未分组**（`list_task_ids_in_group(None)`），不是「全部」—— 传错会误伤别的组。

门禁顺序（与 `/generate_notes` 一致）：`scope` 合法性（`code=400`）→ 转写就绪（`code=300102` / `reason=transcriber_model_not_ready`）→ 磁盘（`code=300104` / `reason=insufficient_disk_space`）→ `_get_circuit_breaker().reset()`（用户主动重试即熔断复位）。

### 4.4 前端

- `BillNote_frontend/src/services/note.ts`：`retryFailedTasks(scope, groupId)`。**范围由后端算**，前端只把「当前可见范围」翻译成一次请求。
- `BillNote_frontend/src/pages/HomePage/components/History.tsx`：工具条加「重试失败」按钮（`RotateCcw` 图标，`variant="outline"`），作用于当前可见范围（`activeGroupId === null` → `scope: "all"`；否则 `scope: "group"` + `toApiGroupId(activeGroupId)`）。
- 超过 `RETRY_CONFIRM_THRESHOLD = 200` 条先弹确认 Dialog（复用既有 `Dialog` 组件，不引新依赖）—— 重试会真的重新下载 + 转写，点错一次的代价是几十条长任务一起跑。
- 前端**不自己筛「哪些失败了」**，选中的范围整个发给后端：两处各判一次必然会漂移，而漂移的表现是「点了重试但什么都没发生」。
- 汇报三类结果，各自一条 toast；门禁类错误由请求拦截器自动弹（`res.code !== 0` → `toast.error(res.msg)`），前端只 `console.warn` 兜底，避免重复提示。

### 4.5 不把 retry 放进 store 的理由

`removeTasks`（spec 010）进 `taskStore` 是因为它需要**乐观移除本地任务**；重试没有本地变更（任务从「失败」变「排队中」由轮询接管），组件直接调 service 更简单、少一层间接。

## 5. 用户决策

| 议题 | 决策 | 理由 |
| --- | --- | --- |
| `retry_scope` | 按当前可见范围重试（m02911） | 按钮放工具条，作用于当前可见范围；不需要先手动勾选 |
| `retry_mode` | **原地重试**：复用同一个 `task_id` 与分组（m02911） | 用户要的是「那条失败的再跑一遍」，不是「列表里多出一条」 |
| `retry_params` | 沿用创建时的 `payload_json`（m02911） | 回落默认值的表现是「重试出来的笔记参数不对」，很难被发现 |
| `retry_bulk` | 超过 200 条先确认（m02911） | 重试会真的重新下载 + 转写，代价高 |

## 6. 已知取舍

1. **`read_task_status` 与 spec 010 的 `task_cleanup.read_task_status` 是两份实现**。两者都读同一个文件、都返回 `Optional[str]`，但**失败语义不同**（删除那边「读不到」= 不在执行 = 可删；这边「读不到」= 不重试），所以没有合并。这与 spec 010「收敛成唯一删除实现」的教训方向相反，是刻意区分：那条教训针对的是**同一判定有两份互相矛盾的实现**，而这里两份的字面逻辑相同、语义归属不同。
2. **`retry_failed_tasks` 是同步阻塞的**。它逐条读状态文件 + 逐条入队，200 条约几十毫秒；入队本身只是往 `_DISPATCH_POOL` 丢引用，不等任务跑完。
3. **老库行（无 `payload_json`）只能按 bilibili `video_id` 重建 URL**，其它平台重建不了 → 跳过并告知原因，而不是拿默认参数硬跑。
4. **重试不重置任务的自动重试计数**。`_execute_note_with_retry` 的 `NOTE_MAX_RETRIES` 是每次执行独立的，所以重试会重新拿到完整的 3 次自动重试机会 —— 这是期望行为，但意味着「反复手动重试」可以无限循环，后端不做频次限制。

## 7. 验证

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` | **619 passed, 2 warnings, 13 subtests passed**（基线 603，+16） |
| spec 011 目录 | `cd backend; .venv\Scripts\python.exe -m pytest tests/011-failed-task-retry -q` | **16 passed** |
| 前端测试 | `cd BillNote_frontend; pnpm test` | **5 files / 24 tests passed** |
| 前端构建 | `cd BillNote_frontend; pnpm build` | **✓ built in 49.03s**，`BUILD_EXIT=0`（仅既有 chunk >500 kB 警告） |
| 前端类型 | `cd BillNote_frontend; pnpm exec tsc -p tsconfig.app.json --noEmit` | **110 errors**（HEAD 基线 192，净减 82；改动文件零命中） |
| 路由挂载 | `create_app(contextlib.nullcontext)` 列路由 | `POST /api/retry_failed_tasks` 在册 |
| pi-lens | `lens_diagnostics mode=full paths=[...]` | `task_retry.py` **0 blocking**、`note.py` **0 blocking**、`History.tsx` 0 blocking |

> [!IMPORTANT]
> **前端类型门禁的坑**：根 `BillNote_frontend/tsconfig.json` 是 solution 式配置
> （`{"files": [], "references": [...]}`），不传 `-b`/`-p` 时 `tsc` 只解析空文件集 →
> **恒 exit 0、零输出**。真正的门禁是 `pnpm exec tsc -p tsconfig.app.json --noEmit`。

### 7.1 本轮修掉的缺陷

**`NOTE_OUTPUT_DIR` 有两个所有者（测试污染仓库）。** `backend/app/routers/note.py:121` 是**字符串**版本（`task_retry._note_output_dir()` 延迟 import 读它），`backend/app/services/note.py:66` 是 **`Path`** 版本（`NoteGenerator._update_status` 真正写 `<task_id>.status.json` 的那一个）。测试只 monkeypatch 了 routers 那个 → `test_retry_writes_pending_status` 读 tmp_path 里的旧副本而断言失败（`assert 'FAILED' == 'PENDING'`），同时状态文件被写进仓库的 `backend/note_results/`。修法：fixture 两个都重定向。`note_results/` 已被 `.gitignore:316` 忽略，无 git 污染，产物已清理。

**`missing` 可能未绑定。** `retry_failed_tasks` 首版把 `missing = []` 写在 `else:` 分支内，后面跟着一个死占位符 `if wanted is not None: pass`。`task_ids=None`（整库）时 `stats["missing"]` 引用的就是未绑定名。教训：`if <cond>: pass` 占位符往往是分支作用域绑定已经出错的信号。

**`?p=0` 无效地址。** `_fallback_payload` 原本用 `tail.isdigit()` 守卫 `int(tail)`：`isdigit()` 只说明「全是数字字符」，`"00"` 能通过并拼出 `?p=0`。改成 `try: parsed = int(tail) / except ValueError: parsed = 0` 并加 `parsed > 0` 判断 —— 顺带也让 pi-lens 的 `ast-grep:unchecked-throwing-call-python`（纯语法启发式，不认 `isdigit()` 这类前置守卫）不再误报。
