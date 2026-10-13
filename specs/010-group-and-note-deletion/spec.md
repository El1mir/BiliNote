# 010 · 分组与笔记的删除

- **状态**：implemented
- **日期**：2026-10-05
- **范围**：删除分组时的两种语义（只删组 / 连组内笔记一起删）、前端多选笔记批量删除、进行中任务的删除守卫
- **上游**：001（批量导入与并发隔离）、005（任务阶段进度）、009（批量分组与长批量健壮性）

## 1. 背景

用户原话（m02362）：「加入一个删除组时可以选择删除组内全部笔记还是单独删除组的功能，然后还需要一个能多选笔记删除选中的功能」。

现状有三个问题。

**（一）删除分组只有一种语义。** `POST /note_group/delete`（`backend/app/routers/note_group.py:127`）只解绑：`delete_group`（`backend/app/db/note_group_dao.py:140-162`）先把组内任务的 `group_id` 置空再删组行。前端 `BillNote_frontend/src/pages/HomePage/components/History.tsx:377-392` 的确认弹窗把这句话写死成文案「组内的笔记不会被删除，它们会被移动到「未分组」。」。用户想连笔记一起删时，只能进组一篇一篇点。

**（二）多选只能用于下载。** `BillNote_frontend/src/pages/HomePage/components/NoteHistory.tsx:148-166` 的复选框条件是 `task.status === 'SUCCESS' && onSelectionChange`，label 是「加入批量下载」；选中集合 `selectedIds`（`History.tsx:49`）唯一的消费者是「下载选中」。要删 20 篇笔记就得点 20 次。

**（三）删除没有进行中守卫。** `delete_task_record`（`backend/app/routers/note.py:1729`）直接删 DB 行 + 5 类派生文件，不看任务是否还在跑。删掉正在跑的任务会留下一个孤儿：DB 行和 `<task_id>.status.json` 都没了，工作线程却还在写结果文件、继续占着下载与转写资源，而它在任何列表里都不可见 —— 用户既看不到它，也删不掉它（列表里没有这一行）。

第（三）点还有一个更隐蔽的形态。`_enqueue_task`（`backend/app/routers/note.py:738-778`）只写 DB 行、**不写状态文件**；`backend/app/services/note.py:277` 的 `self._update_status(task_id, TaskStatus.PARSING)` 才是第一次写状态文件。一次 200 条的批量里，绝大多数任务长期停在「已进池、还没轮到」——**光看状态文件完全看不见它们**。而 dispatch 池只有 8 个位置（spec 009 ticket 02），排在后面的要等很久。这段时间里用户点「删除选中」，删掉的全是还在池子里的任务。

## 2. 目标

1. 删除分组时可以二选一：只删组（笔记退回未分组）或连组内笔记一起彻底删除。
2. 前端可以多选笔记并批量删除，整批只打一次后端请求。
3. 进行中的任务不能被删除（单条与批量统一）。
4. 删除分组时遇到进行中的笔记：跳过它、其余照删，并把跳过原因如实告诉用户。
5. 「删干净」只有一份实现 —— 不允许出现第二份会各自漂移的「什么算删干净」。

## 3. 非目标

- 不做回收站 / 软删除 / 撤销。删除即不可恢复，UI 必须说清楚。
- 不给批量删除加进度条：1000 条的删除请求实测在秒级完成（纯本地文件 unlink + SQLite 删除）。
- 不修 `/delete_task`（`backend/app/routers/note.py:958`）这个空壳。它是按 video_id+platform 删的旧入口，已无调用方，保留为 no-op 存根。
- 不改容量边界（spec 009 ticket 07）对 `note_output` 的清理策略。

## 4. 设计

### 4.1 唯一的删除实现：`backend/app/services/task_cleanup.py`

「删掉一个任务」以前只有一份实现，内联在 `routers/note.py` 的 `delete_task_record` 里。spec 010 要求「删除分组时可以连组内笔记一起删」——如果那时再抄一份，就会出现两份会各自漂移的「什么算删干净」。`backend/app/utils/video_reader.py` 的 Windows `os.rename` 缺陷正是这么来的（读路径与写路径各有一份「条目是否可用」的判定，两份都错，于是损坏条目永远修不好）。所以这里收敛成唯一实现，路由层只负责参数校验与响应包装。

```python
TASK_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    ".json", ".status.json", "_transcript.json", "_audio.json", ".gpt.checkpoint.json",
)

def delete_task_completely(task_id: str, *, allow_in_flight: bool = False) -> Dict[str, Any]:
    """返回 {"task_id", "removed", "files"}；removed=0 表示本来就没这条记录，不算失败。"""
```

`_output_dir()` **延迟** `from app.routers import note as note_router` 再取 `Path(note_router.NOTE_OUTPUT_DIR)`，而不是自己再 `os.getenv` 一份。原因：测试用 `monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp)` 覆盖结果目录；如果本模块自己读环境变量，monkeypatch 就管不到它，删除会打到真实目录 —— `IMAGE_OUTPUT_DIR` 之前正是这么把测试产物写进仓库的。模块级 import 会造成循环依赖（`routers/note.py` 要 import 本模块），所以放在函数里。

### 4.2 进行中守卫：两个信号

`is_task_in_flight(task_id)` 命中任一即为进行中：

1. **本进程的运行登记表**（`_RUNNING_TASKS` + `threading.Lock`）。任务被丢进执行池**那一刻**登记（`mark_task_running`），跑完或异常退出时注销（`unmark_task_running`）。这是唯一能覆盖「已排队但还没开始跑」的信号，而那恰恰是 200 条批量里最长期的状态。
2. **状态文件**：`<task_id>.status.json` 存在且状态不是 SUCCESS/FAILED。文件不存在或损坏 → 读不出状态 → 按可删处理（不能因为一个坏文件把任务锁死）。

登记必须发生在 **submit 那一刻**而不是工作线程真正开始跑的时候：

```python
def _dispatch_note_task(task_kwargs: dict) -> None:
    task_id = str(task_kwargs.get("task_id") or "")
    mark_task_running(task_id)
    try:
        _get_dispatch_pool().submit(_run_note_task_guarded, task_kwargs)
    except Exception:
        unmark_task_running(task_id)   # 否则这条任务永远删不掉
        logger.error(...)
```

注销放在 `_run_note_task_guarded` 的 `finally` 里，所以**抛异常也会注销**：

```python
def _run_note_task_guarded(task_kwargs: dict) -> Any:
    task_id = str(task_kwargs.get("task_id") or "")
    mark_task_running(task_id)
    try:
        return run_note_task(**task_kwargs)
    finally:
        unmark_task_running(task_id)
```

单条路径（`/generate_note`）也从 `background_tasks.add_task(run_note_task, **task_kwargs)` 改成 `background_tasks.add_task(_run_note_task_guarded, task_kwargs)`，两条路径共用同一份登记逻辑。

**刻意不用「DB 行存在」兜底。** 一个很自然的想法是「DB 行在、状态文件不在 → 大概还在跑 → 不给删」。但容量边界会把 `note_output` 整个纳入清理候选（`backend/app/services/media_resource_service.py:743-770`），状态文件可能先于 DB 行消失。那种任务在列表里显示成「等待中」，若被判成进行中就会**永远删不掉**，而前端也没有别的出口 —— 这是一个死路。有了运行登记表就不再需要这个粗糙的兜底。

### 4.3 删除分组：两种语义

`GroupDeleteRequest` 加 `delete_tasks: bool = False`。`delete_tasks=True` 时逐个彻底删除组内笔记，**进行中的跳过**：

```python
for task_id in list_task_ids_in_group(data.group_id):
    try:
        delete_task_completely(task_id)
        deleted_tasks.append(task_id)
    except TaskInFlightError as exc:
        skipped_tasks.append({"task_id": task_id, "reason": str(exc)})

# 刻意放在删任务之后：这样 affected 正好是「退回未分组」的条数（= 被跳过的那些）。
affected = delete_group(data.group_id)
```

返回 `{"affected", "deleted_tasks": [...], "skipped_tasks": [{"task_id", "reason"}]}`。

删除动作**刻意不放进 `note_group_dao`**：`db/` 层不该 import `services/`，否则依赖方向就反了。dao 只更新了模块 docstring 说明新的 opt-in 行为。

### 4.4 批量删除端点：`POST /delete_task_records`

- `BatchDeleteRequest{task_ids: list[str]}`；空列表 → `code=400`；`> MAX_BATCH_DELETE = 1000` → `code=400`。
- `seen` 字典去重**保序**（用户的选择顺序就是删除顺序，结果列表要能对得上）。
- **逐条隔离**：一条失败不影响其余。`_valid_task_id` 失败 → `failed.append({"task_id":…, "error":"任务标识无效"})`；`TaskInFlightError` → `str(exc)`；其他异常 → warning + `str(exc)`。批量接口最怕「重试一次还是全挂」。
- 返回 `{"deleted": [task_id, ...], "failed": [{"task_id", "error"}], "removed_rows": int, "files": [name, ...]}`。**`deleted` 是 task_id 字符串列表**（后端已展平），不是字典列表 —— 前端只需要知道哪些成了。
- `_TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")`：task_id 会直接拼进文件名，路径分隔符与超长串必须挡在路由层。

### 4.5 前端

- **`BillNote_frontend/src/utils/taskStatus.ts`**（新增）：`FINISHED_TASK_STATUSES = ['SUCCESS','FAILED']`、`IN_FLIGHT_TASK_STATUSES`（7 个已知进行中状态）、`isTaskInFlight(status)`。文档串写明「真正的判定在后端，前端这份只用来把明显删不掉的入口置灰」。
- **`isTaskInFlight` 列举已知进行中状态，而不是「不在终态里就算进行中」。** 后一种写法遇到后端新增的状态会一律判成进行中，于是一批任务在前端的删除入口全被置灰 —— 而用户没有别的出口，那就是死路（§4.2 里已经踩过同一个坑的镜像：那边是「存在性 ≠ 有效性」，这边是「非终态 ≠ 进行中」）。列举法遇到未知状态会放行，交给后端拒绝并给出原因，最坏也只是一次「任务仍在执行」的 toast。这条由 `BillNote_frontend/tests/010-group-and-note-deletion/taskStatus.test.ts` 钉住。
- **多选放开到全部任务**：`NoteHistory.tsx` 的复选框条件从 `task.status === 'SUCCESS' && onSelectionChange` 改为 `onSelectionChange`，label 从「加入批量下载」改为中性的「选中」（现在同时服务下载与删除）。
- **单条删除**：`disabled={isTaskInFlight(task.status)}`，Tooltip 文案 `'生成中，暂不能删除'` / `'删除'`。
- **全选只覆盖当前可见任务**：`allVisibleSelected = visibleTasks.length > 0 && visibleTasks.every(t => selectedIds.includes(t.id))`。选中看不见的笔记再删，是最容易误伤的操作。`completedIds` 因此被删掉。
- **批量删除走 store 的 `removeTasks(ids)`**：乐观删除本地状态，**整批一次请求**。1000 条逐条请求会把浏览器连接池和 SQLite 写锁一起打满。
- **如实汇报失败条目**：`removeTasks` 返回后端的 `BatchDeleteResult`，`failed` 非空时 `toast.error(\`${failed.length} 篇未能删除：${failed[0].error}...\`)`。批量删除最忌讳「看起来成功了，其实有几条没删」。
- **前端不在本地过滤进行中的任务**：选中的 id 全部发给后端，由后端逐条返回 `deleted`/`failed`。两边各判一次必然会漂移，而漂移的表现就是「点了删除但什么也没发生」—— 用户最没法排查的那种。
- **删除分组弹窗**加红色警示复选框「同时删除组内的全部笔记（不可恢复；生成中的笔记会被保留并移入未分组）」，`DialogDescription` 随勾选状态切换文案，关闭时重置为未勾选（避免下次误删）。

## 5. 用户决策（m02432）

| 问题 | 选择 | 影响 |
| --- | --- | --- |
| `checkbox_scope` | **放开到全部任务** | 复选框出现在所有任务上（不只 SUCCESS），「全选已完成笔记」改为「全选」 |
| `inflight_delete` | **拒绝删除进行中任务** | 单条与批量统一；`code=300106` |
| `group_inflight` | **跳过进行中，其余删掉** | 跳过的条目随 `skipped_tasks` 返回，前端如实告知 |

## 6. 已知取舍

- **「进行中」的判定是进程级的。** 多进程部署（`uvicorn --workers N`）时，A 进程登记的任务在 B 进程看来不在册；B 进程仍能靠状态文件判出它，但「已排队、还没轮到」的任务在 B 进程眼里是可删的。本项目是单进程（`backend/main.py:125-129`），且 spec 009 的非目标明确不引入任务队列中间件，故接受。真要修，得把登记表落到 DB 或加进程间租约。
- **删除不可恢复。** 没有回收站。UI 用红色警示复选框 + 明确文案承担这个风险。
- **`/delete_task` 仍是空壳。** 无调用方，留着不修。

## 7. 验证

测试落在 `backend/tests/010-group-and-note-deletion/`（24 用例）与
`BillNote_frontend/tests/010-group-and-note-deletion/`（3 用例）。

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` | **603 passed, 2 warnings, 13 subtests passed**（基线 579，**+24**） |
| spec 010 目录 | `.venv\Scripts\python.exe -m pytest tests/010-group-and-note-deletion -q` | **24 passed** |
| 前端单测 | `cd BillNote_frontend; pnpm test` | **5 files / 24 tests passed**（基线 4 files / 21 tests，**+1 file / +3 tests**） |
| 前端构建 | `pnpm build` | `✓ built in 56.95s`，`BUILD_EXIT=0`（仅既有 chunk >500 kB 警告） |
| 前端类型 | `pnpm exec tsc -p tsconfig.app.json --noEmit` | 110 errors（HEAD 基线 192）；**改动文件零命中** |
| pi-lens | `lens_diagnostics mode=full refreshRunners=cheap paths=[...]` | 改动文件 **0 blocking** |
| 路由挂载 | 真实 app 列路由（`create_app(contextlib.nullcontext)`） | `/api/delete_task_records`、`/api/delete_task_record`、`/api/note_group/delete` 均在册 |

最后一行是刻意补的：测试自建 `FastAPI()` + `include_router(prefix="/api")`，与
`backend/app/__init__.py:17-28` 的真实挂载方式一致 —— 但「一致」这个前提本身也要验，
否则测试全绿而生产 404。

> **前端类型门禁的坑**（spec 009 §10.1 已记录，这里再引一次）：根 `tsconfig.json` 是
> solution 式配置（`{"files": [], "references": [...]}`），不传 `-b`/`-p` 时 `tsc` 只解析
> 空文件集 → 恒 exit 0、零输出。真正的门禁是
> `pnpm exec tsc -p tsconfig.app.json --noEmit`；`package.json` 里没有任何 typecheck 脚本，
> `pnpm build`（vite）也不做类型检查。
