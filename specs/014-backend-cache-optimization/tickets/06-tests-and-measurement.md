# 06 · 测试基建、四条不变量用例与前后对比测量

- **依赖**：ticket 01–05 全部完成
- **关联**：spec 014 §测试要点；§12.4（修订）、决策 9、10
- **状态**：resolved 2026-10-14
- **⚠️ 2026-10-14 修订**：范围不变。仅按新范围更新引用（`cache_registry` → `task_status_cache`；只读端点从 4 个降到 1 个；`test_cache_registry.py` → `test_task_status_cache.py`）。

## 目标

把「缓存真的有效、且没让任何东西退化」变成可复现的证据：一套测试基建 + 四条不变量用例 + 与基线同口径的前后对比数字。

## 背景

**本仓库目前没有 `conftest.py` / `pytest.ini` / `pyproject.toml`**（见 `backend/tests/009-batch-grouping-and-long-run-robustness/test_video_task_index.py` 的说明），所有 fixture 都用 pytest 内建。内存注册表是跨用例的全局状态，同一进程里跑多个用例会互相污染——本 ticket 新建本仓库**第一份测试基建** `backend/tests/014-backend-cache-optimization/conftest.py`，不要在别处另起一套。

基线（工单 01 已固定，前后必须用同一命令、同一 N 对比）：

```bash
cd backend
.\.venv\Scripts\python.exe tests\014-backend-cache-optimization\baseline_measure.py --tasks 200 --repeat 5
```

**口径警告（必须遵守）**：`app/` 下有 Cython 编译产物（如 `app/utils/__init__.cp311-win_amd64.pyd`），C 实现绕过 `builtins.open` 与 `os.stat`，因此**这些路径的 `open` 计数偏低，`stat` 计数才是可信口径**。所有前后对比以 `stat` 为主，`open` 只作辅证。基线的 `open=0` 类数字（如 `/task_list` 的 `open_calls_per_call: 0.0`）就是这个盲区的产物，不要拿它当「没有读盘」的证据。

## 改动点

1. **`conftest.py`（新建）**：
   - autouse fixture 在每个用例**前后**调 `task_status_cache.clear()`，不依赖写用例的人记得清。
   - 提供一个清 `BILINOTE_CACHE` 环境变量的 autouse fixture，避免上一个用例的开关泄漏到下一个。
   - 提供 `temp_output_dir` / `temp_db` 类 fixture 的公共实现（临时 SQLite + 临时 `NOTE_OUTPUT_DIR`），供各用例复用——**不要碰真实用户库**。
   - **注意**：`disabled()` 每次读环境变量（ticket 01 的取舍），所以清环境变量必须真的用 `monkeypatch.delenv`，不能只重置模块状态。
2. **四条不变量用例**（每条一个用例，失败时能直接定位是哪条契约被破坏）：
   1. **删除后不返回旧值**——删除某 task_id 后立刻查询其状态，必须返回未知/占位，而不是删除前的值。
   2. **重试后能看到新状态**——同一 task_id 重跑后立刻查询，必须看到新状态，而不是注册表里的 FAILED。
   3. **重启后能读回**——清空进程内注册表（模拟重启）后，进行中任务仍能从落盘投影恢复到可读状态。
   4. **并发不产生半截文件**——并发写时读者始终能 `json.loads` 成功，不会读到半截 JSON。
3. **缓存关闭开关的对比用例**：`BILINOTE_CACHE=off` 时同一路径的 `stat` 计数回到基线量级（证明开关真的生效，否则前后对比会失真）。
4. **前后对比测量**：
   - 用 `BILINOTE_CACHE=off` 再跑一次基线脚本，作为「关缓存」对照组；开缓存跑一次作为实验组。
   - 输出一张对比表：`端点 × stat/次（前） × stat/次（后） × p50（前） × p50（后）`，写入 `backend/tests/014-backend-cache-optimization/after-result.json`。
   - 对比结论要写成**机制**而不是「更快了」：例如「轮询从每轮 899.8 stat 降到 X，因为终态任务命中内存注册表后不再 stat」。
   - **`/task_list` 的收益要拆开报**：「合并两次读」与「换 `orjson`」各贡献多少（ticket 04 要求单独可测），否则无法判断哪一半有效。
5. **回归门禁**：后端全量 `backend\.venv\Scripts\python.exe -m pytest` 不低于历史基线 **653 passed**（`specs/013-local-transcriber-hardware-acceleration/spec.md:65`）；若前端轮询契约有变则补 `pnpm build`。

## 验收

- 四条不变量用例全绿。
- 前后对比表里，`POST /api/task_status/batch`（基线 **899.8 stat/轮**）与 `GET /api/task_list`（基线 **1183.6 stat**、p50 **78.09ms**）的 `stat` 计数显著下降；`transcriber_models_status`（若 ticket 05 做了）TTL 内第二次请求 `stat` 为 0。
- `BILINOTE_CACHE=off` 时数字回到基线量级（开关有效）。
- 全量 `pytest` ≥ 653 passed。
- `after-result.json` 与 `baseline-result.json` 结构一致、可直接 diff。
- spec 014 的实现清单状态更新，spec 状态改 `implemented`。

## 测试

- `conftest.py`（新建，autouse 清注册表 + 临时库/临时输出目录）。
- `test_cache_invariants.py`：四条不变量（**纯新增**，spec 014 的契约文件）。
- `test_cache_switch.py`：`BILINOTE_CACHE=off` 直通与计数回归（**纯新增**）。
- 其余用例分布在各 ticket 自己的测试文件里（`test_task_status_cache.py`、`test_task_status_memory_authority.py`、`test_single_writer.py`、`test_invalidation_hooks.py`、`test_task_list_single_read.py`、`test_transcriber_models_status_cache.py`），本 ticket 负责把它们纳入统一基建并跑通。

---

## Comments

### 实施记录（2026-10-14）

| 改动点 | 落地情况 |
| --- | --- |
| 1. `conftest.py` | ✅ **已在 ticket 01 建立**，ticket 03 补 `results_dir`，ticket 05 补两个 autouse fixture（模型扫描缓存 / 下载状态）。本 ticket 未再改。 |
| 2. 四条不变量用例 | ✅ 新建 `test_cache_invariants.py`（4 用例），**并且真的抓到一个缺陷**——见下。 |
| 3. 缓存开关对比用例 | ✅ 新建 `test_cache_switch.py`（4 用例）。 |
| 4. 前后对比测量 | ✅ 新建 `make_after_report.py` + `after-result.json`（见下）。 |
| 5. 回归门禁 | ✅ 全量 **777 passed**（历史基线 653）。 |

### 🔴 不变量 ④ 抓到一个真实缺陷（**既有代码**，本 ticket 修掉）

写完 `test_invariant_4_concurrent_writers_never_expose_a_partial_file` 第一次跑就红了，而且是**121 次**读到不完整内容：

```
AssertionError: 121 次并发读异常，前几条：["投影文件不是合法 JSON：JSONDecodeError('Expecting value: line 1 column 1 (char 0)')", ...]
ERROR app.services.note - 写入状态文件失败 (task_id=inv4-task)：[WinError 5] 拒绝访问。: '...\inv4-task.status.json.a5216ae5.tmp' -> '...\inv4-task.status.json'
```

**根因链**：

1. `_update_status` 写唯一的临时文件后调 `os.replace(temp, target)`；
2. 目标文件此刻若正被别的线程打开（截图池有 8 个 `screenshot_*` 线程写同一个 task_id，HTTP 轮询线程在同时读），Windows 抛 `WinError 5 (ACCESS_DENIED)`；
3. **原来的代码在 `except` 里降级成「原地覆盖」**：`status_file.open("w")` 会先截断再写 → 读者在窗口内读到空文件或半截 JSON。

即：**唯一会产生半截文件的路径，正是那个号称「兜底」的降级路径。** 这是既有代码（`os.replace` + 原地覆盖兜底在 ticket 02 之前就是这样），与本次缓存改动无关，但它让 spec 014 的不变量 ④ 实际不成立。

**修法**（`backend/app/services/note.py`）：

- 新增 `_replace_with_retry(temp_file, status_file)`：`os.replace` 失败重试 5 次、每次间隔 10ms（`_STATUS_REPLACE_ATTEMPTS` / `_STATUS_REPLACE_DELAY_SECONDS`）。毫秒级占用在重试窗口内基本都会过去。
- **删掉原地覆盖兜底**。失败时就什么都不做，让磁盘上的投影停在上一次的**完整**值：内存注册表才是权威，且本函数有 ~35 个调用点，下一次状态更新马上会重试落盘。「不写」的代价是投影短暂偏旧，「乱写」的代价是读者拿到垃圾 —— 后者更糟。

修完实测：**torn = 0**（同一用例、同样 6 写 ×20 次 ×3 读线程）。

⚠️ 用例里还有一类**不计入断言**的现象：读者侧瞬时 `PermissionError` / `FileNotFoundError`（实测 132 次）。那是「能不能读」而不是「内容完不完整」—— Windows 上替换一个正被打开的文件时，读者侧会拿不到句柄；生产读者 `_read_task_status` 对两者都是容忍的（返回 `None` 走占位）。写方要负责的是**绝不留下半截内容**，这一点现在由代码结构保证，而不只是靠重试运气。

### 关于「有意重叠」

`test_cache_invariants.py` 的四条不变量在各自 ticket 的测试文件里已有更贴近实现层的用例（每条 docstring 里都点名了）。重叠是**刻意的**：

- 契约文件（本文件）是**最外层那一遍**，只走公开入口，不读实现就能自证「四条契约还成立」；
- 实现层用例才会告诉你具体哪一行坏了。

代价是 4 个短用例重复覆盖；收益是任何一条契约被破坏时，失败信息直接指向契约编号，而不是让人去猜某个深层断言属于哪条。

### 前后对比测量

`make_after_report.py` 读 `baseline-result.json`（`--cache both` 一趟跑出两条腿），产出 `after-result.json`。

**「前」怎么取**（这是本 ticket 最容易做错的地方）：

- **受开关管辖**的三条路径（`POST /task_status/batch`、`GET /task_status/{id}`、`GET /transcriber_models_status`）：「前」= **同一次运行的 `BILINOTE_CACHE=off` 那一腿**。改动就发生在「先查注册表」这一步，关掉开关走的就是改动前的路；同一次运行、同一台机器、同一批数据，比跨运行比更可信（本 spec 已经被跨运行的污染坑过一次，见 ticket 02 Comments 的 `sys.modules` 事故）。
- **不受开关管辖**的改进（`/task_list` 的合并读 + orjson）：「前」= **同一次运行内的 A/B**（`measure_task_list_breakdown` 同测「两次读」与「合并一次读」；`measure_orjson_benefit` 在同一份 bytes 上只比解析），端点级再取 `baseline-result.pre-ticket04.json` 的 cache-off 腿。

**对照表**（N=200）：

| 端点 | stat 前 | stat 后 | p50 前 | p50 后 | 倍数 |
| --- | --- | --- | --- | --- | --- |
| `POST /api/task_status/batch`（200 条/轮） | 1260.8 | **12.4** | 166.97ms | **5.52ms** | **30.25×** |
| `GET /api/task_status/{id}` | 22.8 | 12.2 | 3.31ms | 3.07ms | 1.08× |
| `GET /task_list`（整表） | 1970.6 | **908.6** | 162.27ms | **78.80ms** | **2.06×** |
| `GET /transcriber_models_status` | 82.4 | **7.0** | 6.88ms | **1.32ms** | **5.21×** |
| `/api/sys_health` | 278.6 | 310.8 | 39.97ms | 39.48ms | 1.01×（**明确不做**） |
| `/api/deploy_status` | 301.0 | 324.2 | 40.34ms | 39.74ms | 1.02×（**明确不做**） |
| `/api/transcriber_config` | 29.8 | 39.2 | 4.85ms | 4.70ms | 1.03×（**明确不做**） |
| `_update_status`（写一次） | 14.0 | 14.2 | 1.75ms | 1.64ms | 1.07×（未改动） |

`/task_list` 拆解：合并两次读 **112.68ms → 60.67ms**（stat/行 7.67 → 4.09）；orjson 单独 **159.88ms → 54.49ms（2.93×，200 个真实文件 / 16.6MB）**。

（这张表是**写完不变量 ④ 的修复之后**重跑的那一趟：`generated_at = 2026-10-15T01:02:59`。修复只动 `os.replace` 失败后的行为与重试，正常路径上不生效，所以与修前那一趟的差异都在噪声内。）

**机制**（不是「更快了」）：

- 批量轮询：终态任务命中进程内注册表后不再 `os.path.exists`；冷启动一轮仍是 167.28ms / 834 stat，与关缓存等价 —— 收益来自**命中**而不是「少做事」。
- `/task_list`：`_task_title_from_file` 与 `_task_has_note` 读的是同一个 `note_results/<id>.json`、做同一遍解析，合成一次读；解析换成 `orjson`。
- 只读端点：目录扫描进 5s 槽后归零；残留的 7.0 stat/次来自 `visible_model_names()` 读注册表，**刻意不缓存**。

### 证据

- `backend/tests/014-backend-cache-optimization`：**98 passed**（缓存契约 13 + 内存权威 24 + 失效挂载点 11 + `/task_list` 28 + 只读端点 14 + **不变量 4** + **开关 4**）。
- 全量后端回归：**777 passed, 5 warnings, 13 subtests passed in 79.01s**（历史基线 653）。
- `after-result.json` 与 `baseline-result.json` 结构一致（都含 `generated_at` + `results` 数组，`after-result.json` 多出 `comparison` / `task_list_split` / `how_to_read` 三块，`results` 取缓存开那一腿），可直接 diff。
- pyright：`app/services/note.py` 仍是 **29 条既有错误**（逐条核对行号，**没有一条落在本次新增的 `_replace_with_retry`（约 L182–L205）或 `_update_status` 落盘块内**）；`test_cache_invariants.py` / `test_cache_switch.py` / `make_after_report.py` **0 errors**。
- ruff：`app/services/note.py` 仍是既有 2 条（`F811` 重复导入 `AudioDownloadResult`、`E722` 裸 `except`），已用 `git show HEAD:` 证实。
- `git diff backend/requirements.txt` 为空 —— **全程零新增依赖**。

## Answer

**已完成**：四条不变量各一个用例（`test_cache_invariants.py`）、开关语义四条（`test_cache_switch.py`）、前后对比报告（`make_after_report.py` → `after-result.json`，含 `端点 × stat 前 × stat 后 × p50 前 × p50 后` 与 `/task_list` 的合并读 / orjson 拆解）。测试基建复用 ticket 01 建立的 `conftest.py`，未另起一套。

**最重要的产出不是表里的数字，而是不变量 ④ 抓到的那个既有缺陷**：`_update_status` 在 `os.replace` 失败时降级成原地覆盖，是并发下唯一会产生半截状态文件的路径。已改成「重试 + 绝不原地覆盖」，实测 torn 从 121 次降到 0。

**门禁**：`stat` 计数（主判据）在三条受管辖路径上分别降到 13.0 / 轮、12.2 / 次、6.6 / 次；`BILINOTE_CACHE=off` 对照组回到基线量级（batch ~1190 stat/轮）；全量回归 777 passed ≥ 653。

