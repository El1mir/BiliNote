# 05 · 只读端点缓存（**只做 `transcriber_models_status`**）

- **依赖**：01 ✅ resolved 2026-10-14、02 ✅ resolved 2026-10-14（失效契约：写即失效，不允许 TTL 覆盖下载状态）
- **关联**：spec 014 §12.3（修订）、决策 6（已被推翻范围）
- **状态**：resolved 2026-10-14
- **⚠️ 2026-10-14 修订**：原 ticket 要求给**四个**端点各加 5s TTL。审核后**砍到 1 个**。理由见下。

## 目标

给 `GET /transcriber_models_status` 加进程内短 TTL 缓存，消除「下载模型进行中每 3s 一次全模型目录扫描」的开销。**其余三个端点不做。**

## 为什么砍到 1 个

按 **用户 m00596「浏览器访问为主，桌面端很少用」** 逐一核对「浏览器用户是否真的承受这个开销」：

| 端点 | 实测 p50 | 浏览器用户是否承受 | 结论 |
| --- | --- | --- | --- |
| `/sys_health` | 38.18ms | ❌ 5s 轮询**只在 Tauri 挂**（`BillNote_frontend/src/components/BackendHealth/BackendHealthIndicator.tsx:31` `if (!isTauri) return`）。浏览器探活走 `/sys_check`，它只返回 `R.success()`、**不查任何外部依赖**（`backend/app/routers/config.py:655-661`），且**只在启动期轮询、就绪即停**（`BillNote_frontend/src/hooks/useCheckBackend.ts:126-129` `markReady(); return`） | **不做** |
| `/deploy_status` | 39.14ms | ⚠️ 仅**开着设置页监控页**时 30s 一次（`BillNote_frontend/src/pages/SettingPage/Monitor.tsx:42`）。38ms × 每 30s ≈ 0.13% 占用 | **不做** |
| `/transcriber_config` | 4.47ms | ❌ **切设置页才调一次**，4.47ms | **不做**（为它加缓存是过度设计） |
| `/transcriber_models_status` | 6.51ms | ⚠️ 仅**下载模型进行中**时 3s 一次（`BillNote_frontend/src/pages/SettingPage/transcriber.tsx:190-197`）。下载是用户主动发起且会盯着的场景，且开销是**每个可见模型一次 `iterdir()` 目录扫描** | **做** |

**30s × 38ms 不值得加缓存；4.47ms 的一次性调用更不值得。** 原 ticket 把这四个并列，依据是「开销都来自外部探测」——这个判据漏掉了**频率**这一半。

## 改动点

1. `backend/app/routers/config.py` `get_transcriber_models_status`（:419-445）：加一个**模块级 `(timestamp, value)` 单槽缓存**，TTL = 5s。
   - 5s 的依据：与前端下载中的 3s 轮询同量级，不会让状态「晚两个周期」才可见。
   - 实现仍**按函数粒度**，不用 HTTP 中间件（决策 8：中间件无法按端点定制失效，且会误伤写端点）。
2. **下载触发路径必须显式失效**（决策 7），不能只靠 TTL：`backend/app/routers/config.py` 的模型下载端点（`background_tasks.add_task(_do_download_whisper, ...)` 附近，:600-603）在启动下载后立刻清掉该槽。
   - 理由：这是用户主动点击，必须立刻看到反馈。
3. `BILINOTE_CACHE=off` 时直通（复用 ticket 01 的判定函数）。
4. **不引入新依赖**；`cachetools.TTLCache` 在这个规模下不划算（单个槽位，5 行代码即可）。

## 验收

- TTL 窗口内第二次请求：`stat` 计数从基线 **86.0** 降到 ≈0（**以 `stat` 为准**，`open` 计数因 Cython 产物不可信）。
- 下载触发后的**第一次**请求必须反映「下载中」（不被旧槽挡住）。
- TTL 过期后重新扫描（用 monkeypatch 推进时间或直接 sleep，二选一，测试里注明取哪种）。
- 响应字段与基线逐字段一致（`whisper` / `mlx_whisper` / `mlx_available` 三项结构不变）。
- 若日后桌面端占比上升，`/sys_health` 与 `/deploy_status` 按同样模式补上——**但不在本 ticket 范围**。

## 测试

- `backend/tests/014-backend-cache-optimization/test_transcriber_models_status_cache.py`：
  - TTL 内第二次请求不触发目录扫描（`stat` 计数断言）。
  - 下载触发后立刻失效。
  - `BILINOTE_CACHE=off` 时不缓存。

---

## Comments

### 实施记录（2026-10-14）

| 位置 | 改动 |
| --- | --- |
| `backend/app/routers/config.py:2` | `import time` |
| `backend/app/routers/config.py:7` / `:12` | `from typing import Any, Optional`；`from app.services import task_status_cache` |
| `backend/app/routers/config.py:421-423` | `_MODELS_STATUS_TTL_SECONDS = 5.0` |
| `backend/app/routers/config.py:432` | `_MODELS_STATUS_CACHE: dict[str, Any] = {"at": 0.0, "downloaded": None}` |
| `backend/app/routers/config.py:435` | `_invalidate_models_status_cache()` |
| `backend/app/routers/config.py:445` | `_scan_downloaded_models(model_names) -> dict` |
| `backend/app/routers/config.py:471-477` | `get_transcriber_models_status` 改为 `names` 取一次 + `_scan_downloaded_models(names)` + `status_row(size, downloaded_map.get(size, False))` |
| `backend/app/routers/config.py:593-594` / `:644-645` | 两个下载函数加 `finally: _invalidate_models_status_cache()` |
| `backend/tests/014-backend-cache-optimization/conftest.py` | 新增两个 autouse fixture：`_clean_models_status_cache`、`_clean_model_download_state` |
| `backend/tests/014-backend-cache-optimization/test_transcriber_models_status_cache.py` | 新增 **14 用例** |
| `backend/tests/014-backend-cache-optimization/baseline_measure.py` | 新增 `measure_transcriber_models_status`（冷/热两态）与对应打印 |

零新增依赖（`requirements.txt` 未改）。

### ⚠️ 设计偏离：缓存只包住**目录扫描**，不包住**下载状态**

ticket 改动点 1 写的是「模块级 `(timestamp, value)` 单槽缓存」+ 改动点 2「下载触发路径必须显式失效」——这两条合起来隐含了**整个响应进缓存**。

实施时改成只缓存扫描结果，理由：`dl_state`（`backend/app/transcriber/model_download_state.py`）本来就是**进程内内存态**，`status_row()` 只是一次 dict 查询，直读成本为零；把它一起缓存只会让「下载中 / 已完成 / 失败」晚一个周期才可见 —— 那就违背了本 ticket 的初衷（省扫描开销，不是让 UI 变迟钝）。改了之后：

- **「下载触发后第一次请求必须反映下载中」自动成立** —— 下载状态压根不在槽里，不需要在触发时失效（ticket 改动点 2 因此没有按原样实施）；
- 失效改挂**下载流程收尾**（`finally`，成功 / 失败 / 「已经下好不重复下」三种出口都走），因为**那才是磁盘上真值发生变化的时刻**。

ticket Comments 里这条偏离对应两个用例钉住：`test_downloading_state_is_never_cached`、`test_failed_state_is_visible_without_waiting_for_ttl`。

### 实测（N=200，`--cache both`，`/transcriber_models_status` 冷/热两态）

| | p50 | stat/次 |
| --- | --- | --- |
| 改动前的基线（每一次调用都是一次完整扫描） | **6.51ms** | **86.0** |
| 缓存**关**：cold → warm | 7.26ms → 7.32ms | 82.8 → 83.6（无变化，开关确实生效） |
| 缓存**开**：cold → warm | 6.80ms → **1.25ms** | 85.8 → **6.6** |

即命中态 **stat 85.8 → 6.6（−92.3%）、p50 6.80ms → 1.25ms（5.4×）**。缓存关的那一列是阴性对照：同一份代码、同一个端点在 `BILINOTE_CACHE=off` 下 warm 与 cold 完全一致，说明收益确实来自槽而不是测量噪声。

### ⚠️ 残留的 6.6 stat/次，以及为什么不再往下做

验收原文写「stat 计数从基线 86.0 降到 ≈0」，实测降到 **6.6** 而非 0。残量来自端点自己：

```python
names = list(get_registry().visible_model_names())   # ← 每次都读注册表文件
```

`visible_model_names()` 要读并解析自定义模型注册表，本身要 stat。把它也缓存就跨到了另一个成本中心，而且要新增两条失效（`POST /whisper_models` `backend/app/routers/config.py:187` 与 `DELETE /whisper_models/{name}` `:198`），代价是「用户刚加的自定义模型 5s 内不出现在列表里」。

**这里选择不做**：收益是 6.6 次 stat ≈ 0.1ms，代价是一类新的 UI 陈旧。已作为后续可选项记录，不在本 ticket 范围。

### 测试

`backend/tests/014-backend-cache-optimization/test_transcriber_models_status_cache.py`（14 用例）：

- 缓存本体：首次扫描 3 个可见模型 / TTL 内第二次 0 次扫描 / **命中时整轮请求的 `os.stat` 调用为 0**（主验收）/ TTL 过期重新扫描 / **读操作不延长 TTL**（TTL 从上次扫描算起）/ `cache_off` 时每次都扫。
- 失效：下载完成 / 下载失败 / 「已经下好不重复下」早退分支 —— 三种出口都断言「收尾后下一次请求必须重扫」。
- 下载状态不被缓存：`mark_downloading` → `downloading: true`；`mark_done` → 立刻 `false`；`mark_failed` → `failed: true` + `error` 透传，均**不等待 TTL**。
- 响应契约：顶层键 `{whisper, mlx_whisper, mlx_available}` 不变；每个 whisper 行的键固定为 `{model_size, downloaded, downloading, failed}`；非 Darwin 上 `mlx_whisper == []`、`mlx_available is False`；`downloaded` 确实来自扫描结果。

测试手法两点说明：

1. **时间推进不用假时钟**：缓存读 `time.monotonic()`，全局打补丁会波及别的模块。改为 `monkeypatch` 把 `_MODELS_STATUS_TTL_SECONDS` 改小（0.05–0.15s）+ 真 `time.sleep`（毫秒级，套件仍只需 7.7s）。
2. `scans` fixture 可以强制扫描结果（`scans.result = False`），否则用例会随**这台机器上真的有没有下过 whisper 模型**而飘 —— 这是刻意的：本机 `backend/models/` 下可能真的有模型。

conftest 新增两个 autouse fixture 的原因与 ticket 01 相同：两者都是**跨用例的进程内全局状态**。`model_download_state` 没有 `clear()`，fixture 直接快照/复原它的 `_status` / `_errors` 两个 dict。

### 证据

- `backend/tests/014-backend-cache-optimization`：**90 passed**（缓存契约 13 + 内存权威 24 + 失效挂载点 11 + `/task_list` 28 + 本 ticket 14）。
- 全量后端回归：**769 passed, 5 warnings, 13 subtests passed**（历史基线 653，无退化）。
- pyright：本 ticket 新增/改动的文件 **0 新增错误**。`backend/app/routers/config.py` 仍报 2 条 `Import "torch" could not be resolved`（`:164`、`:731`）—— **既有问题**，已用 `git show HEAD:backend/app/routers/config.py` 证实两个 `import torch` 都在文件里（torch 未装进 venv）。
- ruff：`backend/app/routers/config.py` 报 1 条 `F401 fastapi.HTTPException imported but unused`（`:6`）—— 同样用 HEAD 版本证实**既有**，未动。

### ⚠️ 工具陷阱：`backend/app/routers/config.py` 是 CRLF

「改文件」在本 ticket 上踩了两次坑，记下来给后续：

- `config.py` 是 **CRLF**（777 行全是），而 `note.py`、`tests/014-*` 全是 LF。`str_replace_editor` 的**多行** `old_str` 在 CRLF 文件上**匹配不到**（单行能中），而且它会往 CRLF 文件里插 LF 行 —— 造成混合行尾。
- 最终做法：用一段一次性 Python 脚本（先把 `\r\n` 归一成 `\n`、做替换、再整体写回 `\r\n`）改写，保证除目标改动外行尾不变。结果：`git diff --stat` = **60 insertions / 5 deletions**，行尾 CRLF=777 / LF-only=0。

### 观测到的一次测量噪声（非本 ticket 引入）

测量脚本 cache-off 那一轮的日志里出现一次：

```
[ERROR] app.services.note - 写入状态文件失败 (task_id=task-000141-...)：[WinError 5] 拒绝访问。: '...\task-000141-....status.json.99aaf7cc.tmp' -> '...\task-000141-....status.json'
```

这是 `_update_status` 的**既有**落盘回退路径（Windows 上 temp 目录里的瞬时 rename 失败），脚本按设计继续跑完、结果正常；与本 ticket 的改动无关（改的是 `routers/config.py`，不是状态写入）。

## Answer

**已完成**：给 `GET /transcriber_models_status` 的**目录扫描**加了 5s 进程内单槽缓存（`_scan_downloaded_models`，`backend/app/routers/config.py:445`），下载流程收尾处显式失效（`finally`，`:593` / `:644`）。实测命中态 **stat 85.8 → 6.6**、**p50 6.80ms → 1.25ms**；`cache_off` 阴性对照证实收益来自槽本身。

**两条偏差**（都已在上面论证）：① 缓存只包扫描、不包下载状态 —— 所以「下载触发后立刻反映下载中」不靠失效钩子，而是靠下载状态根本不进缓存；② 残留 6.6 stat/次 来自 `visible_model_names()` 读注册表，**选择不继续优化**（收益 ≈0.1ms，代价是新增两类 UI 陈旧）。

**范围守住**：`/sys_health`、`/deploy_status`、`/transcriber_config` 三个端点按 ticket 的判定表**明确不做**。

