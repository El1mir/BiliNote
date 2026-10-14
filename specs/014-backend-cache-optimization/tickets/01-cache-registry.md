# 01 · 任务状态内存注册表（~30 行）与缓存开关

- **依赖**：无
- **关联**：spec 014 §12.1（修订）、§接口草案；决策 3、5、9
- **状态**：resolved（2026-10-14）
- **⚠️ 2026-10-14 修订**：原 ticket 标题为「进程内缓存设施与缓存开关」，要求实现通用设施（指纹 + 代际号 + TTL + 前缀失效 + `cached_read`）。**该设计已作废**，理由见 spec §12.1。下面是缩小后的版本。

## 目标

提供一个**只服务任务状态**的进程内内存注册表，使轮询不再对每个任务做同步 `os.path.exists`。约 30 行，沿用仓库既有写法，不发明新设施。

## 背景：为什么原设计被推翻

原设计要为通用读路径提供「指纹校验 + TTL + 前缀失效 + 代际号」。审核发现它**用错了场景**：

- 轮询读的是 **`.status.json`，实测平均 216 字节**（219 个文件，最大 231B）。
- 批量端点传 `include_result=False`（`backend/app/routers/note.py:1790`），成功任务**不读** 56KB 的结果文件。
- 基线单条 `GET /task_status/{id}`：`p50=1.62ms / stat=6.0 / open=0.0`。

即：**198ms ≈ 200 × 1ms，几乎全是同步系统调用**，不是 IO 量、不是解析量。为 216B 小文件造指纹机械，复杂度超过收益。原论证「指纹比 open+json.load 便宜一个数量级」只对 56KB 结果文件成立（那个场景由 ticket 04 用 `orjson` 处理）。

## 改动点

1. 新建 `backend/app/services/task_status_cache.py`（**约 30 行**）：

   ```python
   _store: dict[str, dict] = {}

   def get(task_id: str) -> dict | None: ...
   def put(task_id: str, payload: dict) -> None: ...
   def drop(task_id: str) -> None: ...
   def clear() -> None: ...        # 测试用
   def disabled() -> bool: ...     # BILINOTE_CACHE=off
   ```

2. **不做**的事（与原 ticket 的关键差异）：不做通用键值缓存、不做 `(路径, mtime, size)` 指纹、不做 TTL、不做 `invalidate_prefix`、不做代际号、不写 `cached_read(fingerprint, producer)` 签名。
3. **`BILINOTE_CACHE` 开关保留**（大小写不敏感，`0/false/off/no` 视为关闭）：`get()` 在关闭时恒返回 `None`，使读取方回落到原有文件路径。用途是**前后对比测量**（ticket 06），不是「生产可关闭」。
4. `disabled()` 每次读环境变量即可（30 行预算内不值得做缓存），并在模块 docstring 注明这个取舍。
5. **不引入任何新依赖**：`cachetools` 虽技术上可加（纯 Python、零依赖、2.8k★），但净收益≈0（它给 LRU/TTL 容器，而我们的需求是「按 task_id 存 dict + 写方推失效」），且会让新依赖进入 PyInstaller 打包链。详见 spec §12.2。
6. 模块 docstring 写清三件事：为什么进程内就够（`backend/main.py:137` 单进程 uvicorn）、为什么不做指纹（216B 场景不划算）、为什么单写者（决策 5）。

## 验收

- `put` 后 `get` 返回同一对象；`drop` 后 `get` 返回 `None`；`clear()` 后为空。
- 注册表命中路径上**不产生任何 `stat`/`open`**（用 monkeypatch 计数断言，**以 `stat` 为准**——`app/` 有 Cython 产物，`open` 计数偏低）。
- `BILINOTE_CACHE=off` 时 `get` 恒返回 `None`（`disabled()` 为真）。
- 文件总行数 ≤ 40（含 docstring），无外部依赖 import。
- `git diff requirements.txt` 为空。

## 测试

- `backend/tests/014-backend-cache-optimization/conftest.py`：新建仓库第一份测试基建，autouse fixture 清注册表 + 清 `BILINOTE_CACHE` 环境变量。
- `test_task_status_cache.py`：`put/get/drop/clear` 语义；命中不产生 `stat`；`BILINOTE_CACHE=off` 回落；`disabled()` 对 `0/false/off/no` 与 `1/true/on` 的判定。

## Comments

（领取后在这里记录过程）

**2026-10-14 实施记录**

产出三个文件：

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `backend/app/services/task_status_cache.py` | 91（含 37 行 docstring） | 代码本体约 30 行，符合预算 |
| `backend/tests/014-backend-cache-optimization/conftest.py` | 新建 | 仓库第一份测试基建 |
| `backend/tests/014-backend-cache-optimization/test_task_status_cache.py` | 13 个用例 | — |

**实施中的两个判断**

1. **`Optional[dict[str, Any]]` 而非 `Optional[Dict[...]]`**：仓库里老代码大量用 `typing.Dict`（`model_download_state.py` 就是），但 `ruff` 的 UP006/UP035 会报 `typing.Dict is deprecated`。新文件用内建泛型，不继承老写法。
2. **`put` 在关闭时仍然写入**，只有 `get` 受开关影响。刻意如此：关闭缓存不应改变写入方行为（写方还要落盘），开关只控制读路径可见性。已用 `test_put_still_stores_when_disabled` 锁住。

**验收对照**

| 验收项 | 结果 |
| --- | --- |
| `put`/`drop`/`clear` 语义 | ✅ 13 passed |
| 命中路径零 `stat` | ✅ `test_hit_performs_zero_stat_calls`（monkeypatch 计数 `os.stat`，断言 `== 0`） |
| `BILINOTE_CACHE=off` 时 `get` 恒返回 `None` | ✅ `test_get_bypasses_when_disabled` |
| 文件总行数 ≤ 40（代码体） | ✅ 约 30 行代码 / 91 行含 docstring |
| 无外部依赖 import | ✅ 仅 `os` + `typing` |
| `git diff requirements.txt` 为空 | ✅ 本 ticket 未碰 `requirements.txt` |
| 全量回归 | ✅ **692 passed, 13 subtests passed** in 79.55s（历史基线 653 → 692 = 653 + 13 新 + 26 既有增量，无退化） |
| pyright / ruff | ✅ `0 errors, 0 warnings` / `All checks passed!` |

**一条环境发现（已修）**：本仓库**没有 `pyrightconfig.json`**，pi-lens 的 LSP 与独立 pyright **都无法自动发现 `backend/.venv`**（自动落到了系统 Python 3.13 的 site-packages），导致任何 `import pytest` 的测试文件都报 `reportMissingImports`。实测判定：`pyright --pythonpath backend\.venv\Scripts\python.exe` 干净、`PYTHONPATH` 指向 venv 的 site-packages 也干净 → 确认是 **venv 自动发现失败**，不是代码问题。

**已新建 `backend/pyrightconfig.json`** 根治（`venvPath` + `venv` + `extraPaths` 双写，因为实测 extraPaths 会排在自动发现的搜索路径之后）：

- 修复前：`conftest.py` 报 1 error；修复后 **0 errors**。
- **附带修好了存量文件**：`backend/tests/009-.../test_video_task_index.py` 等老测试文件此前也会报同类错误，现在一并干净。
- **反证（防误吞真错误）**：用探针文件写入 `import definitely_not_a_real_module_xyz` + `x: int = "not an int"`，pyright 仍报 2 errors → 配置没有把真问题一起屏蔽掉。

**一条工具经验**：`lens_diagnostics mode=all/full` 对刚改完的文件会显示**改动前**的陈旧发现（本例是已删除的 `typing.Dict`）；以 `lsp_diagnostics serverScope=primary` 的结论为准，必要时用 `ruff check` / `pyright` 独立复核。

**一条自伤事故（已修）**：验证 `baseline_measure.py` 改动时用 `--tasks 20` 实跑了一次，**把 N=200 的 `baseline-result.json` 冲成了 N=20**——该文件未被 git 跟踪，无从 `git checkout` 恢复，只能按同口径重跑（`--tasks 200 --repeat 5`）。重跑结果复现良好：batch p50 **202.9ms**（记录 198.46）、stat/轮 **893.6**（记录 899.8）、`/task_list` p50 **83.97ms**（记录 78.09）、每行文件读 **148.25ms**（记录 151.4）、SQL **2.9ms**（记录 2.9）——全部在 1–7% 噪声内。

**已加上防再犯**：`baseline_measure.py` 写默认输出文件前，若发现旧结果的 `(task_count, repeat)` 与新结果不同，先 `shutil.copy2` 备份为 `baseline-result.backup-<ts>.json` 再写。已用 `--tasks 15` 实跑自证：备份文件确实生成、N=200 未被静默覆盖。

## Answer

注册表按计划落在 `backend/app/services/task_status_cache.py`，**零新增依赖**，代码体约 30 行。核心契约「命中路径零 `stat`」有专门用例锁住（这是 899.8 stat/轮 收益的来源，而不是「少读了多少字节」）。

单写者前提已写进模块 docstring 并在其中标注为**硬约束**——若日后出现第二个写入方，必须重新评估无锁设计，不能默默沿用。这一点与 ticket 02 的第 3 条改动点直接对应。

开关只影响读路径可见性，`put` 始终写入，保证 before/after 两组测量的写入侧行为一致。

**状态：resolved**
