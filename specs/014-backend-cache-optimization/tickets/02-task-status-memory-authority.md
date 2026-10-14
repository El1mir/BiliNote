# 02 · 任务状态改为内存权威 + 单写者收敛

- **依赖**：ticket 01（任务状态内存注册表）— ✅ resolved 2026-10-14
- **关联**：spec 014 §12.4（修订）、决策 3、5；§接口草案「改造：任务状态读写」
- **状态**：resolved 2026-10-14
- **⚠️ 2026-10-14 修订**：范围不变，但**收益理由与验收口径改了**——原 ticket 写「使 stat 计数与任务数量无关，省掉重复读盘」，这把危害说成了 IO 量。真实危害是**同步系统调用阻塞单进程事件循环**。详见 spec §12.1/§12.4。

## 目标

把任务状态从「每任务每轮同步 `os.path.exists`」改成「纯内存字典查找」，**消除事件循环阻塞**；并把状态写入收敛为单写者。

## 背景（修订版）

`backend/app/routers/note.py:1695` `_read_task_status` 每个任务每次轮询都要 `os.path.exists` + `open` + `json.load`。N=200 时实测 **198.46ms/轮**、**899.8 stat/轮**，且**与任务是否在动无关**。

**为什么危害不是「IO 量」**：轮询读的是 `.status.json`，实测平均 **216 字节**（219 个文件，最大 231B）；批量端点传 `include_result=False`（`note.py:1790`），成功任务**不读** 56KB 的结果文件。基线单条 `GET /task_status/{id}` 是 `p50=1.62ms / stat=6.0 / open=0.0`。

**所以**：198ms ≈ 200 × 1ms，**开销几乎全在同步 `os.path.exists` 系统调用上**。在单进程 uvicorn（`backend/main.py:137` `reload=False`）里，这意味着**每 3 秒有 200 个任务的同步 stat 阻塞事件循环**——进行中的下载/转写/LLM 请求都要排在它后面。改成纯 dict 查找后，这个阻塞**归零**，这才是本 ticket 的价值。

（顺带：这也是为什么本 ticket **不需要**指纹机制——省下的不是解析时间。）

状态写入在 `backend/app/services/note.py:1466-1522` `_update_status`：构造 dict → 写 `<task_id>.status.json.<uuid8>.tmp` → `temp_file.replace(status_file)`，`json.dump(..., ensure_ascii=False, indent=2)`，失败回退非原子写。约 35 处调用，含截图逐张回报（`backend/app/services/note.py:2128`）。

五处直接读状态文件的模块（改动时必须全部照顾到）：
`backend/app/routers/note.py:1695`、`backend/app/services/task_recovery.py:89`、`backend/app/services/task_retry.py:107`、`backend/app/services/task_cleanup.py:115`、`backend/app/services/media_resource_service.py:529`。

## 改动点

1. `_read_task_status(task_id, include_result=True, unknown_is_none=False)`：
   - **先查 `task_status_cache.get(task_id)`**（纯 dict 查找，零系统调用）；未命中才走原有文件路径（**不做指纹校验**——机制已作废）。
   - 终态任务（`SUCCESS`/`FAILED`）写入后长期命中。
   - 保持既有返回契约不变：`_STATUS_LIGHT_KEYS` 逐 key 提取、`payload.setdefault("message", "")`、`SUCCESS` 且 `include_result` 时补 `payload["result"]`、状态文件缺失但结果文件存在时合成 SUCCESS payload、`unknown_is_none` 决定返回 `None` 还是 `_pending_status(task_id)`。
   - **注意**：`GET /task_status/{task_id}`（`include_result=True`）会读 56KB 结果文件——**这部分不进注册表**，注册表只存 `_read_task_status` 的轻量 payload。详情页本来就不是高频路径。
2. `NoteGenerator._update_status`：
   - **先 `put` 进内存注册表**（权威），再落盘（投影）。
   - 落盘保留「唯一临时文件 + `os.replace`」的原子不变量——读者绝不能看到半截文件。
   - 落盘失败沿用现有非原子写回退，但**不能让内存与落盘不一致到读出错误状态**：内存是权威，所以失败只影响「重启后读回」。
3. **单写者收敛**：截图线程池（`backend/app/services/note.py:2128`）改为投递到主循环，使 `_update_status` 只有主循环一个调用方。
   - **不加锁**：单写者 + GIL 下 dict 的单个 `__setitem__` 是原子的，业务逻辑不需要额外锁。
   - **⚠️ 修订**：原 ticket 写「注册表本身不加锁（dict 内部操作由 `cache_registry` 的锁保护）」——`cache_registry` 通用设施已作废，30 行的注册表**没有锁**。这个取舍现在完全依赖「单写者」，所以第 3 条从「顺带收敛」变成**本 ticket 的正确性前提**：先做单写者，再让读取方依赖无锁 dict。
4. **保住重启恢复**：`task_recovery.py` 启动扫描（DB + 状态文件）必须仍能重建内存注册表。进程启动时注册表为空，一切从投影文件读回——这是「重启后能读回」这条不变量的实现方式。

## 验收

- **主判据（修订）**：N=200 时 `POST /api/task_status/batch` 的 **`stat` 计数**从基线 **899.8/轮** 降到**接近 0**（终态任务稳定命中后每轮增量为 0）。
  - **以 `stat` 为准**，`open` 计数不可信（`app/` 有 Cython 产物绕过 `builtins.open`）。
- 返回体逐字段与基线一致（`status`/`stage`/`stage_label`/`progress`/`stage_progress`/`message`/`updated_at`）。
- 单任务 `GET /api/task_status/{id}` 行为不变（含 `include_result` 时返回完整 markdown）。
- 未知 task_id 仍按既有语义处理（`unknown_is_none=True` 返回 `None`；否则回落 `_pending_status` 或 `_task_row_exists` → `_pending_status`）。
- 并发截图回报不再产生多写者（断言 `_update_status` 调用方唯一性，或断言并发写后读者始终能 `json.loads` 成功）。

## 测试

- `test_task_status_memory_authority.py`：
  - 写入后立即读，返回新值（不是投影文件里的旧值）；
  - 终态任务第二次读不产生 `stat`（monkeypatch 计数，**以 `stat` 为准**）；
  - **内存与投影不一致时以内存为准**（原「指纹变化触发重读」用例已删除——指纹机制作废）；
  - 注册表被清空（模拟重启）后能从投影文件读回。
- `test_single_writer.py`：并发写场景下读者不读到半截 JSON（不变量 ④）。

---

## Comments

### 实施记录（2026-10-14）

| 文件 | 改动 |
| --- | --- |
| `backend/app/services/task_status_cache.py` | **新建**（91 行，代码体约 30 行）：模块级 `_store: dict[str, dict]` + `disabled/get/put/drop/clear` |
| `backend/app/routers/note.py` | `_read_task_status` 改为**内存优先**；抽出 `_light_status_payload`、`_read_result_payload` |
| `backend/app/services/note.py` | `_update_status` **先 `put` 内存、后落盘**（原子替换不变） |
| `backend/app/services/task_cleanup.py` | `delete_task_completely` 在删除产物后 `task_status_cache.drop()` |
| `backend/tests/014-backend-cache-optimization/conftest.py` | autouse 前后双清注册表 + `BILINOTE_CACHE` 环境隔离 |
| `backend/tests/014-backend-cache-optimization/test_task_status_cache.py` | 13 用例（契约 + 开关语义） |
| `backend/tests/014-backend-cache-optimization/test_task_status_memory_authority.py` | 24 用例（快路径零 stat、两路径契约一致、内存不被污染、写路径、失效、并发、端点级） |
| `backend/pyrightconfig.json` | **新建**：让 pyright/LSP 认到 `backend/.venv`（此前落系统 Python 3.13） |

### ⚠️ 改动点 3「单写者收敛」**未实施**（前提被实证推翻）

原 ticket 把「无锁注册表」的正确性押在**单写者**上，并计划把截图线程池（`backend/app/services/note.py:2128`）改为投递到主循环。实施前做了探针（包装 `_update_status` 记录 `threading.current_thread().name`，用假 `generate_screenshot` 逼出真实并发路径），实测：

```text
{"MainThread": 2, "screenshot_0": 1, ..., "screenshot_7": 1}
```

**8 个 `screenshot_*` 线程在并发写同一个 task_id** —— 「单写者」前提不成立。

但结论反转了：`_update_status` 的 `data` 每次都是**整份重建**的完整 payload（`backend/app/services/note.py:1497-1506`），**不是读-改-写**，所以并发只是「最后写的人赢」，写进去的永远是**完整状态**，不存在半截状态或字段互相污染。因此：

- **不加锁的设计仍然成立**，但**理由改写**：「整份替换 + GIL 下 `__setitem__` 原子」，而不是「单写者」。与落盘侧「唯一临时文件 + `os.replace`」是同一个论证。
- 因此**不动截图线程池**（避免为一处不存在的风险改动并发路径）。
- 对应的验收改走本 ticket「验收」第 5 条的**后一个分支**：`test_concurrent_updates_leave_a_complete_payload` / `test_concurrent_readers_never_see_a_partial_payload`（8 写 + 4 读，断言读者的 payload 字段集永远完整）。
- `test_single_writer.py` 未创建；相关用例并入 `test_task_status_memory_authority.py`。

### ⚠️ 测量口径事故：`sys.modules` 清理漏掉顶层 `app` 包（旧基线数字作废）

对比测量第一次跑出来「缓存开 = 缓存关」，排查后定位为**脚本自身的隔离缺陷**，不是实现问题：

`backend/tests/014-backend-cache-optimization/baseline_measure.py` 的清理循环写的是 `if m == "main" or m.startswith("app.")`，而 **`"app".startswith("app.")` 是 `False`** —— 顶层 `app` 包对象存活，`app/__init__.py` 的 `create_app` 继续拿它 globals 里那份**旧** `app.routers.note` 建路由。于是端点所属的是**第二个模块对象**，其 `NOTE_OUTPUT_DIR` 停在默认值 `"note_results"`，读的是仓库真实目录而不是播种的临时目录 → 缓存永不命中。

修法：新增 `_reset_app_modules()`，删除 `main` / **`app` 本身** / `app.*` / `events` / `ffmpeg_helper`，再 `importlib.invalidate_caches()`；`run_one_scale` 改为调用它。

**后果**：ticket 01 记的旧基线（批量 `p50=198.46ms` / `899.8 stat` 每轮）是**污染口径**下测的，**作废**。下表「缓存关」一列才是真基线（旧文件留在 `baseline-result.backup-2026-10-14T234026.json`）。ticket 04/06 复测必须用同一份修好的脚本。

### 验收对照（N=200，`--tasks 200 --repeat 5 --cache both`）

| 指标 | 缓存关（=真基线） | 缓存开 | 变化 |
| --- | --- | --- | --- |
| `POST /api/task_status/batch` p50 | **162.89ms** | **5.37ms** | **约 30×** |
| 同上 p95 | 174.86ms | 5.76ms | 约 30× |
| **`stat`/轮（主判据）** | **1113.0** | **12.8** | **约 87×** |
| `open`/轮 | 240.0 | 4.2 | 约 57× |
| 读入字节/轮 | 70445.8B | 1285.2B | 约 55× |
| 首轮（冷启动） | 167.33ms / stat=807 | 159.65ms / stat=811 | **等价（符合设计）** |

- **主判据达成**：稳态 `stat` 从 1113/轮 降到 12.8/轮（剩下的来自 TestClient 自身），且**与任务数量无关**。
- 冷启动一轮与不缓存等价 —— 注册表空时必须读一次投影文件，这是设计而非回归。
- 其余端点本轮未动（属 ticket 04/05）：`/task_list` 缓存关 `p50=162.27ms`（SQL=2.54ms + 每行文件读=152.64ms）；`sys_health` 40.86/39.24ms、`deploy_status` 41.03/40.18ms、`transcriber_models_status` 6.78/6.71ms、`transcriber_config` 4.98/4.43ms；`_update_status` 写入 1.57/1.51ms、237B。

### 证据

- `backend/tests/014-backend-cache-optimization`：**37 passed**（`test_task_status_cache.py` 13 + `test_task_status_memory_authority.py` 24）。
- 全量后端回归：**715 passed, 5 warnings, 13 subtests passed in 79.70s**（历史基线 653，无退化）。
- 端点级验收用例 `test_batch_endpoint_touches_no_disk_when_warm`：50 条任务预热后 `POST /api/task_status/batch`，断言 `os.path.exists` 调用数 **== 0**（通过）。
- pyright：`task_status_cache.py` + `tests/014-*` 全部 **0 errors**。
- ruff：`backend/app/services/note.py` 报的 2 条（`F811` 重复导入 `AudioDownloadResult`@42、`E722` 裸 `except`@1550）**是既有问题** —— 用 `git show HEAD:backend/app/services/note.py | ruff check` 证实 HEAD 版本同样报这两条（仅行号前移）。
- `git diff backend/requirements.txt` 为空 —— **零新增依赖**。

### 环境发现（写给后续 ticket）

1. **`open` 计数不可信**：`app/` 下有 Cython 编译产物（如 `app/utils/__init__.cp311-win_amd64.pyd`），C 实现绕过 `builtins.open`。**`stat` 计数才是主判据**。
2. `backend/app/routers/note.py:131` 的 `NOTE_OUTPUT_DIR` 是**模块级常量**（导入时固化）。搭建测试 app 时必须先把模块重置干净，否则 `create_app` 会用旧模块（见上面的口径事故）。
3. 本仓库此前**没有** `conftest.py`/`pytest.ini`/`pyproject.toml`，`tests/014-*` 的 conftest 是第一份测试基建。

## Answer

**已实施并验证**：任务状态读取改为「内存权威 + 落盘投影」——稳态 `stat` 从 1113/轮 降到 12.8/轮（约 87×），批量轮询 `p50` 从 162.89ms 降到 5.37ms（约 30×），冷启动一轮与不缓存等价，重启后仍能从投影文件读回（进程启动注册表为空）。

**两处与原 ticket 的偏差（均已在上文取证）**：
1. **不做单写者收敛**：实证 8 个截图线程并发写，但 `_update_status` 是整份替换而非读-改-写，无锁设计因此仍安全；理由由「单写者」改写为「整份替换 + GIL 下 `__setitem__` 原子」。截图线程池不动。
2. **旧基线数字作废**：脚本的 `sys.modules` 清理漏掉顶层 `app` 包，导致产物目录指向仓库真实目录；已修（`_reset_app_modules`），并以修好的脚本重测出上表。

**给 ticket 04/06 的输入**：
- 复测必须用修好的 `baseline_measure.py`（`--cache on|off|both`），且「缓存关」一列才是对照基线。
- `/task_list` 的主要成本是**同一份文件被读两遍**（152.64ms 中大部分），与本次注册表无关，属 ticket 04。
- 代理开关：`BILINOTE_CACHE=off` 可让 `get()` 恒不命中（`put` 仍写），用于同一次运行内做前后对比。

