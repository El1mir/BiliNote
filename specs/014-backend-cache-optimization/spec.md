# Spec 014: 后端缓存优化（轮询 / 落盘 / 只读端点）

- 状态：`implemented`
- 日期：2026-10-14
- 获批：2026-10-14（用户 m00533 选择「改为 approved」）
- 完成：2026-10-14（ticket 01–06 全部 resolved；全量回归 777 passed）
- **⚠️ 2026-10-14 修订（第二次，见 §12）**：用户 m00539 要求审核「是否该复用成熟包 / 哪些改动值得做」。审核推翻了原决策 1、2、6，并把交付范围缩到约 60%。**以 §12 为准。**
- 来源：用户请求（m00002）+ wayfinder 地图 `.scratch/backend-cache-optimization/map.md`（5 张决策 ticket 全部 resolved）
- 边界：用户 m00164 限定为 ① HTTP 响应/一次性读缓存 ② 落盘层（`.status.json`）③ 数据库层。**外部网络出口缓存不在范围内**（见「非目标」）。
- **部署前提（用户 m00596）**：**浏览器访问为主，桌面端（Tauri）很少用**。§12 的取舍以此为前提。

## 背景

前端每 3 秒轮询一次任务状态（`BillNote_frontend/src/hooks/useTaskPolling.ts:53`），并且首页/设置页会调用若干只读端点。基线测量（`backend/tests/014-backend-cache-optimization/baseline_measure.py`，数据见 `baseline-result.json`）把这些路径的真实代价钉死如下（N=200）：

| 端点 | 前端频率 | p50 | p95 | stat/次 | 备注 |
| --- | --- | --- | --- | --- | --- |
| `POST /api/task_status/batch`（200 条） | 3s | **198.46ms** | 253.36ms | 899.8/轮 | 读入 27405B/轮 |
| `GET /api/task_list`（200 条） | 进首页一次 | **78.09ms** | 79.03ms | 1183.6 | 其中 SQL 仅 **2.9ms** |
| `GET /api/task_status/{id}`（单条） | — | 1.62ms | — | 6.0 | |
| `GET /api/sys_health` | 5s（**仅 Tauri**） | 38.18ms | 38.66ms | 303.4 | |
| `GET /api/deploy_status` | 30s（仅开着监控页） | 39.14ms | 41.48ms | 320.6 | |
| `GET /api/transcriber_models_status` | 3s（**仅下载中**） | 6.51ms | 6.7ms | 86.0 | |
| `GET /api/transcriber_config` | 切设置页一次 | 4.47ms | 5.08ms | 39.0 | |
| `NoteGenerator._update_status`（写一次） | 每任务约 35 次 | 1.54ms | 1.64ms | 13.8 | 237B/次 |

三条根因：

1. **轮询是常驻成本，且与负载无关**：198ms × 每 3 秒 ≈ **6.6% 单核占用**。终态任务的状态文件内容根本不变，却被每 3 秒重新 `os.path.exists` + `open` + `json.load` 一次（`backend/app/routers/note.py:1695` `_read_task_status`）。
   - **⚠️ 修订**：原表述为「少读盘」，**不准确**。实测状态文件平均 **216B**（219 个文件，最大 231B），且批量端点走 `include_result=False`（`backend/app/routers/note.py:1790`），成功任务**不会**去读 56KB 的结果文件。单条基线 `p50=1.62ms / stat=6.0 / open=0.0` 说明**开销几乎全在同步 `os.path.exists` 系统调用上**。真正的危害是**每 3 秒 200 次同步 stat 阻塞单进程事件循环**，不是 IO 量。
2. **`/task_list` 的耗时 98% 不在数据库**：SQL 2.9ms vs 每行 `_task_title_from_file` + `_task_has_note` **151.4ms**——同一份结果文件被读两遍（1.03 open/行）。这里读的是**真·大文件**：实测 873 个结果文件共 47.6MB，平均 **55.9KB**、中位 18.1KB。
3. **只读端点的耗时来自目录扫描而非 DB**：`/sys_health`、`/deploy_status` 各 300+ 次 stat。
   - **⚠️ 修订**：这三个端点的轮询**几乎不影响浏览器用户**——`/sys_health` 只在 Tauri 挂（`BillNote_frontend/src/components/BackendHealth/BackendHealthIndicator.tsx:31` `if (!isTauri) return`）；浏览器探活走 `/sys_check`，而它只返回 `R.success()`、不查任何外部依赖（`backend/app/routers/config.py:655-661`），且**只在启动期轮询、就绪即停**（`BillNote_frontend/src/hooks/useCheckBackend.ts:126-129`）。

当前仓库**没有任何缓存基建**（全仓 grep `lru_cache|TTLCache|functools.cache|cachetools` 零命中）。**⚠️ 修订**：原表述为「不能随意加依赖」，**不准确**。真实约束是 PyInstaller 单文件打包（`backend/build.sh`）+ Docker + Tauri 三种形态并存；`cachetools` 这类纯 Python 包技术上可加。**不加它的理由是净收益≈0**（见 §12），不是不能加。

## 目标

1. 把每 3 秒一次的轮询从「每任务同步 stat 落盘文件」改成「纯内存字典查找」，**消除事件循环阻塞**。
2. 消除 `/task_list` 每行对同一文件的两次重复读（这是真·大文件重复解析，收益最实）。
3. ~~给四个外部探测型只读端点加进程内 TTL 缓存~~ —— **⚠️ 修订：降级为可选，见 §12**。
4. 保证正确性：删除、重试、重启恢复三条路径都不会读到陈旧或已删除的状态。
5. 提供可复现的验收口径：同一测量脚本在改动前后跑出可对比的数字。

## 非目标

- **外部网络出口缓存**：B站合集展开 `/expand`、分P、字幕、`/image_proxy` 的上游图片。用户未勾选该边界（m00164）。
- **前端轮询节奏改造**（长轮询 / 变更推送）：属于后端边界之外。
- **多进程 / 多实例支持**：后端是单进程 uvicorn（`backend/main.py:137` `reload=False`），本次不做跨进程失效协议。
- **`/task_list`、`/general/settings`、providers/models 的响应缓存**：前者改为合并重复读，后两者开销是廉价 DB 往返，不做缓存（见 §决策 6）。
- **缓存命中率接入设置页**：留作实现期可选项，不是本次验收条目。

## 已定决策

> **⚠️ 2026-10-14 第二次修订**：决策 1、2、6 已被审核推翻（用户 m00539 要求审核「是否该复用成熟包 / 哪些值得做」）。下方保留原文并标注作废原因，**生效版本见 §12**。

1. ~~**统一进程内缓存设施，每处读路径显式声明缓存键与失效钩子**~~ —— **作废（过度设计）**。原依据「单进程 uvicorn 使进程内一致」仍然正确，但推论错了：轮询读的是 **216B** 小文件，不是重解析场景。实测单条 `stat=6.0 / open=0.0`，说明开销是**同步系统调用**，不是 IO 量或解析量。为它造「指纹 + 注册表 + TTL + 前缀失效 + 代际号」的通用机械，复杂度超过省下的东西。**改为：约 30 行的任务状态专用 dict**（§12.1）。
2. ~~**缓存键形状 = 路径 + mtime + size 指纹**~~ —— **作废**。原论证「指纹比 open+json.load 便宜一个数量级」**仅对 56KB 结果文件成立，对 216B 状态文件不成立**（216B 的 `open+json.load` 本身已接近系统调用开销）。这是原设计最实质的错误。
3. **任务状态改为「内存注册表为权威 + 关键节点落盘」** —— **保留**（理由修正为「消除事件循环阻塞」而非「少读盘」）。`.status.json` 降级为**给其他模块 / 重启后读的投影**。硬约束：必须保住进程重启后读回的能力，否则 spec 009 ticket 03 的重启恢复（`backend/app/services/task_recovery.py`）失效。
4. **失效契约 = 写方推为主，删除路径显式逐条失效**（**去掉「指纹为兵底」**——指纹机制已作废）。批量删除（`backend/app/routers/note.py:2023` `delete_task_records`）必须逐条失效，不能整表清空（部分成功部分失败是既有语义）。不把「删了又冒出来」的复发押在「某处一定会清」上——该症状在 `backend/app/routers/note.py:1994` 已有记载，所以**每条删除/覆盖路径都要有明确的一条失效代码**，并由测试锁住。
5. **收敛为单写者**：截图线程池（`backend/app/services/note.py:2128` 并发调 `_update_status`）改为投递到主循环，内存注册表**不加锁**。「内存为权威」与「单写者」是一对——没有后者，每次改字典都要在锁下进行，收益与复杂度都变差。
6. ~~**只缓存四个外部探测端点**，TTL 均 5 秒~~ —— **降级**。审核发现两点：(a) `/transcriber_config` 实测 4.47ms 且**切设置页才调一次**，为它加缓存是过度设计；(b) 用户 m00596 确认**浏览器访问为主**，而 `/sys_health` 的 5s 轮询**只在 Tauri 挂**（`BillNote_frontend/src/components/BackendHealth/BackendHealthIndicator.tsx:31`）——浏览器用户根本不承受它。**改为：可选加分项，只做 `/transcriber_models_status`（下载中 3s 轮询，且是最大用户的真实场景）**（§12.3）。
7. **下载触发与转录器配置写入路径显式失效**，不依赖 TTL —— **保留**（若 §12.3 不做则不适用）。
8. **缓存实现在进程内、按函数粒度，不用 HTTP 中间件** —— **保留**。理由：中间件无法按端点定制失效语义，且会误伤写端点。
9. **验收口径 = `stat` 计数为主判据，p50 延迟作佐证**（**去掉 `open` 作为对等判据**——见决策 10）。测试形态 = 模块单测 + 端点 smoke；autouse fixture 清缓存；保留 `BILINOTE_CACHE=off` 开关用于 before/after 对比（**注意**：开关的主要用途变为「对比测量」，而非「随时关掉生产缓存」）。
10. **测量口径警告（必须带走）**：`app/` 下有 Cython 编译产物（如 `app/utils/__init__.cp311-win_amd64.pyd`），C 实现绕过 `builtins.open`，因此**这些路径的 `open` 计数偏低，`stat` 计数才是可信口径**。任何前后对比必须用同一口径。

## 待确认问题

无。

（原本的三条不确定项已在地图阶段收敛；§12 的三条修订项亦已由用户 m00596/m00597 拍板。）

## 接口草案

### 新增：任务状态内存注册表（**修订：不再是通用缓存设施**）

`backend/app/services/task_status_cache.py`（新文件，**约 30 行**）

```python
# 模块级 dict + 窄函数出口，沿用 backend/app/transcriber/model_download_state.py 的既有写法
_store: dict[str, dict] = {}

def get(task_id: str) -> dict | None: ...
def put(task_id: str, payload: dict) -> None: ...
def drop(task_id: str) -> None: ...
def clear() -> None: ...            # 测试用
def disabled() -> bool: ...         # BILINOTE_CACHE=off 时 get 恒返回 None
```

约定（写进模块 docstring）：

- **只服务任务状态**，不做通用键值缓存、不做指纹、不做 TTL。
- **写入方唯一**：仅 `NoteGenerator._update_status`（单写者，见决策 5）调用 `put`；读取方仅 `_read_task_status` 调 `get`。
- **`BILINOTE_CACHE=off`**（大小写不敏感，取值 `0/false/off/no`）→ `get` 恒返回 `None`，用于前后对比测量。
- **进程启动即空**：不做落盘恢复；重启后由 `task_recovery.py` 从 DB + 投影文件重建。

### 改造：任务状态读写

`backend/app/routers/note.py`

- `_read_task_status(task_id, include_result=True, unknown_is_none=False)`：**先查注册表**（纯 dict 查找，零系统调用），未命中才走原有文件路径。终态任务（`SUCCESS`/`FAILED`）写入后长期命中。
- `NoteGenerator._update_status`（`backend/app/services/note.py:1466-1522`）：先 `put` 进注册表（权威），再落盘（投影）；落盘保留「唯一临时文件 + `os.replace`」的既有原子不变量。
- `_task_title_from_file(task_id)`（:1904）/ `_task_has_note(task_id)`（:1921）：**合并为一次读**，一次 `read_text` + 一次 `loads` 同时得出 title 与 has_note；`GET /api/task_list` 改为调用合并后的函数。
  - **修订**：这里顺带用上**已装但全仓零使用**的 `orjson==3.10.16`（`orjson.loads` 比标准库快 2–5 倍）。这是真·大文件场景（实测平均 **55.9KB**、中位 18.1KB），orjson 的收益在这里成立。
  - 注意语义：`has_note` 是「`markdown` 是字符串且 `.strip()` 非空」，`title` 走 `_result_title(result)`；两者失败态不同（`""` vs `False`），合并时不能混淆。

### 改造：只读端点（**修订：降级为可选**）

`backend/app/routers/config.py`

- **默认只做** `GET /transcriber_models_status`（:419）——「下载中 3s 轮询」是真实高频场景，且开销来自每个可见模型一次 `iterdir()`。
- `GET /sys_health`（:606）/ `GET /deploy_status`（:664）/ `GET /transcriber_config`（:92）**默认不做**：前两者只在 Tauri 或开着监控页时轮询，后者一次 4.47ms 且切页才调。若日后桌面端占比上升再补（§12.3）。
- 若做 `/transcriber_models_status`：模型下载触发路径必须显式失效，**不能只靠 TTL**（用户点完「下载」要立刻看到反馈）。

### 失效挂载点（必须逐条覆盖）

> **修订**：指纹机制作废后，「兵底」不再存在，因此**每一条删除/覆盖路径都必须有明确的一行失效代码**，并由测试锁住（决策 4）。

| 触发 | 位置 | 动作 |
| --- | --- | --- |
| 状态推进 | `backend/app/services/note.py` `_update_status` | `put` 进内存注册表（权威），关键节点落盘 |
| 单条删除 | `backend/app/services/task_cleanup.py` `delete_task_completely` | `drop(task_id)` |
| 批量删除 | `backend/app/routers/note.py:2023` `delete_task_records` | 逐条 `drop(task_id)` |
| 失败重试 | `backend/app/services/task_retry.py`（复用同一 task_id） | `drop(task_id)` + 重新入队 |
| 模型下载触发（仅 §12.3 做缓存时） | 下载端点 | 失效 `transcriber_models_status` |

## 流程

```text
读路径                              写路径
  |                                   |
_read_task_status(task_id)            |
  |-- get(task_id) 命中 → 返回内存值   |
  |-- 未命中 → 走原有文件路径（stat+open+load）
  |                                   |
  |                              _update_status
  |                                   |-- put(task_id, payload)   ← 权威
  |                                   |-- 落盘 .status.json        ← 投影（原子替换）
  |                                   |
  |                              drop(task_id)  ← 删除 / 重试
```

关键顺序不变量：**不得引入「先清缓存再看文件」的顺序**——必须沿用「原子替换完成后才有完整内容」（`backend/app/services/note.py:1508-1522`）。

## 测试要点

测试目录 `backend/tests/014-backend-cache-optimization/`。**本仓库目前没有 conftest.py**，本次新建 `conftest.py` 作为本仓库第一份测试基建（autouse fixture 清注册表），不要在其他 ticket 里另起一套。

### 四条不变量用例（每条一个）

1. **删除后不返回旧值**：删除某 task_id 后立刻查询其状态，必须返回未知/占位，而不是删除前的值。
2. **重试后能看到新状态**：同一 task_id 重跑后立刻查询，必须看到新状态，而不是注册表里的 FAILED。
3. **重启后能读回**：清空进程内注册表（模拟重启）后，进行中任务仍能从落盘投影恢复到可读状态。
4. **并发不产生半截文件**：并发写时读者不会读到半截 JSON。

### 验收清单（**修订后**）

| 对象 | 断言 |
| --- | --- |
| 任务状态注册表 | 命中时不产生 `stat`/`open`；`clear()` 后为空；`BILINOTE_CACHE=off` 时恒回落到文件路径 |
| `POST /api/task_status/batch` | `stat` 计数显著低于基线 **899.8/轮**（N=200）；返回内容与基线逐字段一致 |
| `GET /api/task_list` | 每行文件读从 2 次合并为 1 次（基线 1.03 open/行 → 目标 ≤0.5）；**p50 从 78.09ms 显著下降** |
| `transcriber_models_status`（若做） | TTL 内第二次请求 `stat` 归零；下载触发后立刻可见 |
| 回归门禁 | 后端全量 `pytest` 不低于历史基线 **653 passed**（`specs/013-local-transcriber-hardware-acceleration/spec.md:65`） |

### 对比命令（前后必须一致）

```bash
cd backend
.\.venv\Scripts\python.exe tests\014-backend-cache-optimization\baseline_measure.py --tasks 200 --repeat 5
```

## 实现清单（**修订后**）

| 工单 | 标题 | 状态 | 修订 |
| --- | --- | --- | --- |
| [01](./tickets/01-cache-registry.md) | 任务状态内存注册表（~30 行）与缓存开关 | **resolved** 2026-10-14 | **缩小**：去掉指纹/TTL/前缀失效/通用设施 |
| [02](./tickets/02-task-status-memory-authority.md) | 任务状态改为内存权威（**不做单写者收敛**，见 ticket Comments） | **resolved** 2026-10-14 | 保留，验收改为「消除事件循环阻塞」；stat 1113→12.8/轮 |
| [03](./tickets/03-invalidation-hooks.md) | 失效挂载点（删除 / 重试） | **resolved** 2026-10-14 | 保留，去掉「指纹兵底」；重试改为「覆盖」而非「drop」（见 ticket Comments） |
| [04](./tickets/04-task-list-single-read.md) | `/task_list` 合并同文件两次读 + `orjson` | **resolved** 2026-10-14 | 保留 + 用上已装的 orjson；验收主口径由 `open/行` 改为 `stat/行`（见 ticket Comments） |
| [05](./tickets/05-readonly-endpoint-ttl.md) | 只读端点缓存（**只做 `transcriber_models_status`**） | **resolved** 2026-10-14 | **大幅缩小**：从 4 个端点降到 1 个；缓存只包目录扫描、不包下载状态（见 ticket Comments） |
| [06](./tickets/06-tests-and-measurement.md) | 测试基建、四条不变量用例与前后对比测量 | **resolved** 2026-10-14 | 保留；不变量 ④ 抓出一个既有缺陷（原地覆盖兜底）并修掉 |

## 12. 第二次修订（2026-10-14，审核结论）

### 12.0 为什么修订

用户 m00539 要求审核：「是否有必要做这些事情，比如写缓存工具，允许复用当前有的已经成熟程度包，审核这六个 ticket 哪几个能使用成熟的包提速或者取代的」。

审核产出三条纠正 + 两条否决，**范围净缩减约 40%**。

### 12.1 作废「通用缓存设施 + 指纹」（推翻决策 1、2）

**错在哪**：原设计用「56KB 结果文件需要重解析」的开销，去论证「216B 状态文件」的方案。实测两者差两个数量级：

- 状态文件：219 个，平均 **216B**，最大 231B；单条基线 `p50=1.62ms / stat=6.0 / open=0.0`。
- 结果文件：873 个，平均 **55.9KB**、中位 18.1KB、总 47.6MB。

批量端点走的是 `include_result=False`（`backend/app/routers/note.py:1790`），成功任务**根本不读结果文件**。所以 198ms ≈ 200 × 1ms，**几乎全是 `os.path.exists()` 的同步系统调用**。

**结论**：为 216B 小文件造「指纹 + 代际号 + TTL + 前缀失效」的通用机械，复杂度超过收益。**改为约 30 行的任务状态专用 dict**，沿用仓库已有的 `model_download_state.py` 写法。

### 12.2 关于「复用成熟包」的结论（回答用户的核心问题）

| 包 | 现状 | 结论 |
| --- | --- | --- |
| `cachetools` | **未装**（纯 Python、零依赖、[tkem/cachetools](https://github.com/tkem/cachetools) 2.8k★，技术上可加） | **不加**。它提供 LRU/TTL 容器，但**不解决我们的核心问题**：键是任务状态、失效是写方推。用了仍要自己写失效挂钩和开关，**省下的只有约 20 行 dict 管理，净收益≈0，却让新依赖进入 PyInstaller 打包链**（`backend/build.sh`） |
| `redis==5.2.1`（已装） | 全仓**零处导入**，docker-compose 里**无 redis 服务** | **不用**。单进程 uvicorn 下进程内 dict 就是全局一致的；引入 redis = 新增一个必须运维的服务，换取我们本就有的一致性 |
| `celery==5.5.1`（已装） | 仅 `from kombu import uuid`（`backend/app/services/provider.py:2` 用来生成 UUID） | **不用** |
| `diskcache` / `aiocache` | 未装 | **不用**。跨进程/异步才有价值，我们没有跨进程问题 |
| `orjson==3.10.16`（已装） | 全仓**零处使用** | **用**。`/task_list` 读的是真·大文件（平均 55.9KB），`orjson.loads` 比标准库快 2–5 倍。**零新增依赖** |

**顺带纠正**：原 spec 写的「不能随意加依赖（离线/轻量部署）」**不准确**。真实约束是 PyInstaller + Docker + Tauri 三种形态并存；`cachetools` 技术上可加，不加的理由是净收益≈0，不是不能加。

### 12.3 缩减只读端点缓存（推翻决策 6 的范围）

按 **用户 m00596「浏览器访问为主，桌面端很少用」** 重新核对（原 `specs/` 注释与最终回答不一致，以后者为准）：**2026-10-14 22:05 用户明确回答「浏览器访问为主，桌面端很少用」**。

| 端点 | 浏览器用户是否承受 | 原计划 | 修订后 |
| --- | --- | --- | --- |
| `/sys_health` | ❌ 否——5s 轮询只在 Tauri（`BackendHealthIndicator.tsx:31`）；浏览器探活走 `/sys_check`，它不查外部依赖（`config.py:655-661`）且**只在启动期轮询、就绪即停**（`useCheckBackend.ts:126-129`） | 缓存 | **不做** |
| `/deploy_status` | ⚠️ 仅开着设置页监控页时 30s 一次 | 缓存 | **不做** |
| `/transcriber_config` | ❌ 切设置页一次，4.47ms | 缓存 | **不做**（原就已建议砍） |
| `/transcriber_models_status` | ⚠️ 仅**下载模型进行中**时 3s 一次 | 缓存 | **做（唯一保留）** |

### 12.4 保留不动的部分

- **决策 3（内存权威 + 落盘投影）**：保留，但**验收理由改了**——收益是「消除事件循环阻塞」，不是「少读盘」。
- **决策 5（单写者）**：保留。
- **决策 4（失效契约）**：保留但去掉「指纹兵底」——指纹已作废，所以**每条删除/覆盖路径都必须有明确的一行失效代码 + 测试锁住**。
- **`/task_list` 合并两次读**：保留，且收益理由是**最实的**（真·大文件重复解析，151.4ms）。
- **ticket 06（测试与对比）**：保留。
