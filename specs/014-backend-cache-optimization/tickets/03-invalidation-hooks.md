# 03 · 失效挂载点（删除 / 重试）

- **依赖**：ticket 01（任务状态内存注册表）— ✅ resolved 2026-10-14；ticket 02（任务状态内存权威）— ✅ resolved 2026-10-14
- **关联**：spec 014 §12.4（修订）、决策 4；§接口草案「失效挂载点」
- **状态**：resolved 2026-10-14
- **⚠️ 2026-10-14 修订**：原有「指纹为兵底 + 写方推作快速路径」的**双层保险已作废**（指纹机制被推翻，见 spec §12.1）。现在是**单层**：每条删除/覆盖路径都必须有明确的一行失效代码。这使本 ticket 的**重要性上升**——不再是「快速路径」，而是唯一保障。
- 顺带：模型下载 / 转录器配置两条只与 ticket 05 相关，已移出本 ticket（见下）。

## 目标

把每一条会**删除或覆盖**任务状态的路径都挂上显式失效。缓存最危险的失败模式不是「没命中」，而是**命中了一个已经不存在或已被覆盖的东西**。

## 背景

几条会删除或复用 task_id 的路径，必须与状态注册表达成明确契约：

1. **删除任务**：`backend/app/services/task_cleanup.py:115` 读状态文件做进行中守卫，`delete_task_completely` 会删掉 `.status.json` / `<task_id>.json` 等派生文件（文件名清单在 `task_cleanup.py:31`）。注册表若不失效，会把**已删除**的任务状态继续返回给前端——症状是「删了又冒出来」，`backend/app/routers/note.py:1994` 附近的注释记录了同一症状。
2. **批量删除**：`backend/app/routers/note.py:2023` `delete_task_records` 逐条隔离删除，部分成功部分失败——失效必须**逐条**，不能整表清空。
3. **失败任务重试**：`backend/app/services/task_retry.py` 复用**同一个 task_id 原地重跑**（`backend/app/routers/note.py:2118` 决策 2 的注释），同一路径被覆盖成一份**新**的状态文件。**注册表的键只有 task_id、没有指纹**，重试后前端会一直看到旧的 FAILED——**这条是本 ticket 最需要测试锁住的路径**。
4. **进程重启恢复**：`backend/app/services/task_recovery.py` 启动时扫描 DB + 状态文件重新入队。进程是新的、注册表是空的——天然安全（本设计不做落盘缓存）。
5. **并发写入**：`_update_status` 用「唯一临时文件 + `os.replace`」保证读者不会看到半截文件。读取必须沿用这个既有不变量。

## 改动点

1. 按 spec §接口草案「失效挂载点」表逐条落实（**单一事实来源**）：

   | 触发 | 位置 | 动作 |
   | --- | --- | --- |
   | 单条删除 | `backend/app/services/task_cleanup.py` `delete_task_completely` | `drop(task_id)` |
   | 批量删除 | `backend/app/routers/note.py:2023` `delete_task_records` | 逐条 `drop(task_id)`（循环内，与单条删除同一入口最稳） |
   | 失败重试 | `backend/app/services/task_retry.py` | `drop(task_id)` + 重新入队 |

2. **失效代码与删除代码放在同一个函数里**，不要分散到调用方——批量删除时逐条独立、互不影响（部分成功部分失败是既有语义）。
3. **不得引入「先清缓存再看文件」的顺序**；必须是「原子替换完成后才有完整内容」。
4. **移出本 ticket**（原属本 ticket，现只与 ticket 05 相关，且 ticket 05 本身是可选）：
   - 模型下载端点失效 `/transcriber_models_status` 缓存；
   - `update_transcriber_config` 失效 `/transcriber_config` 缓存（该端点已决定不做缓存，故此项**整体消失**）。
   若 ticket 05 不做，这两条一并消失。

## 验收

- 删除某 task_id 后立刻查询该 id，返回未知/占位，而不是删除前的值。
- 批量删除 10 条、其中部分失败时，成功删除的那些立刻读不到旧值，失败的那些仍可读。
- **重试后立刻查询，看到的是新状态而不是注册表里的 FAILED**（最高风险路径）。
- 进行中守卫语义不变：进行中任务仍被拒绝删除（`CODE_TASK_IN_FLIGHT = 300106`，`backend/app/routers/note.py:1983`）。

## 测试

- `test_invalidation_hooks.py`：
  - **不变量 ①** 删除后不返回旧值；
  - **不变量 ②** 重试后能看到新状态；
  - 批量删除的部分成功语义；
  - **新增**：断言「每条会删除/覆盖的路径都调用了 `drop`」——用 monkeypatch 计数 + 遍历已知路径，防止日后新增删除路径时漏挂（**这是指纹作废后唯一的结构性保障**）。
- 复用 ticket 01 的 `conftest.py` autouse fixture 清注册表。

---

## Comments

### 实施记录（2026-10-14）

本 ticket 的**代码改动全部在 ticket 02 里已经落地**（`drop` 就在删除函数内部），本次做的是**审计 + 结构性保障**。

| 位置 | 现状 |
| --- | --- |
| `backend/app/services/task_cleanup.py` `delete_task_completely` | ✅ 已经有 `drop(text)`，且**在 `_delete_artifacts` 之后**（含顺序注释） |
| `backend/app/routers/note.py` `delete_task_record` / `delete_task_records` | ✅ 两个端点都走 `delete_task_completely`（批量是循环内逐条调用，天然逐条失效） |
| `backend/app/services/task_retry.py` `retry_failed_tasks` | ✅ `_update_status(task_id, PENDING, message="用户手动重试")`（`task_retry.py:308`）→ 内部 `put`，**先于** `_dispatch_note_task`（:327） |
| `backend/app/services/task_recovery.py` | ✅ 同一个 `_update_status`；且进程启动时注册表为空，天然安全 |
| 新增文件 | `backend/tests/014-backend-cache-optimization/test_invalidation_hooks.py`（11 用例） |
| 测试基建 | `results_dir` fixture 从 `test_task_status_memory_authority.py` **下沉到 `conftest.py`**，三个用例文件共用 |

### ⚠️ 偏差：重试用「覆盖」而不是 `drop`

本 ticket 的改动点表写「失败重试 → `drop(task_id)` + 重新入队」。实施时**没有加这个 `drop`**，理由是它比「覆盖」更差：

- `_update_status` 做的是 `put`（一份**全新完整**的 payload）+ 原子落盘，所以重试一开始注册表里就已经是新状态 `PENDING`，旧的 `FAILED` 被直接盖掉 —— 不变量 ② 达成。
- 若改成 `drop`：注册表清空之后、工作线程第一次写状态之前，**磁盘上的旧 `FAILED` 文件还在**。这期间任何一个轮询都会走文件路径、把**旧的 `FAILED` 读回来重新缓存**，前端表现为「点了重试没反应」。这正是改动点 3 明令禁止的「先清缓存再看文件」。
- 结论：**删除用 `drop`（实体不存在了，文件也没了，读者读到空），覆盖用 `put`（实体还在，新状态立刻可见）**。这条区分已由 `test_retry_overwrites_stale_failure` 与 `test_retry_writes_the_new_state_before_requeueing` 两个用例锁住。

（`drop` 仍然在重试路径上出现 —— 但只在用户**删除**它的时候，走的是 `delete_task_completely`。）

### 审计：谁还会写 `*.status.json`

全仓 grep `status_file` / `.status.json` / `unlink(` 后确认：

- **唯一写入方**是 `NoteGenerator._update_status`（`backend/app/services/note.py:1482-1539`，唯一临时文件 + `os.replace`）。没有任何其它代码直接写状态文件。
- **直接读文件的四个模块**（`backend/app/routers/note.py`、`task_recovery.py:89`、`task_retry.py:107/124`、`task_cleanup.py:115`、`media_resource_service.py:529`）都只是读者，不填注册表 —— 它们是低频路径（启动恢复 / 重试前判断 / 删除守卫 / 容量清理），保持原样。
- `media_resource_service.py` 的 `target.unlink()` / `path.unlink()`（:402/:920/:939）删的是**媒体资源与预览缓存**，不含状态文件，无需挂失效。
- 终态文件里没有「缓存代际号」之类的东西可被绕过 —— 这也再次确认指纹作废后 `drop`/`put` 是**唯一**保障。

### 证据

- `backend/tests/014-backend-cache-optimization`：**48 passed**（缓存契约 13 + 内存权威 24 + 失效挂载点 11）。
- 全量后端回归：**727 passed, 5 warnings, 13 subtests passed in 80.87s**（历史基线 653，无退化）。
- pyright：三个测试文件 + `conftest.py` **0 errors**；ruff：**All checks passed**。
- 关键用例：
  - `test_delete_drops_registry` / `test_batch_delete_drops_every_successful_id` / `test_batch_delete_isolates_failures` —— 不变量 ①；
  - `test_retry_overwrites_stale_failure` —— 不变量 ②（预热 FAILED → 重试 → 立刻读到 PENDING）；
  - `test_all_delete_paths_share_one_chokepoint` —— 结构保障（spy `delete_task_completely`，两个端点 3 条 id 全部经过它）；
  - `test_artifacts_are_removed_before_the_registry_is_dropped` —— 顺序不变量（在 `_delete_artifacts` 入口断言内存仍在，在 `drop` 入口断言文件已删）；
  - `test_in_flight_delete_is_rejected_and_keeps_registry` —— 守卫语义（`CODE_TASK_IN_FLIGHT = 300106`）且不误清缓存。

### 给后续 ticket 的输入

ticket 05（只读端点缓存）若落地，**模型下载完成 / 转录器配置更新**这两条失效要挂到 `backend/app/routers/config.py` 的对应写路径上，本 ticket 已按计划把它们移出（见改动点 4）。

## Answer

**已完成**：审计确认「删除 → `drop`」挂在 `delete_task_completely` 内部（先删投影文件、后删内存），两个删除端点共用这一个入口；重试与恢复走 `_update_status` 的 `put`，天然覆盖旧值。新增 `test_invalidation_hooks.py`（11 用例）把不变量 ①②、批量部分成功语义、进行中守卫、**单一入口**与**顺序**两条结构性保障全部锁住。

**唯一偏差**：重试**不**做 `drop`，改为依赖 `put` 覆盖 —— 因为 `drop` 会开一个「内存已清、磁盘仍是旧 FAILED」的窗口，让轮询把旧值读回来重缓存。已在上文论证并加用例锁定。

