# 04 · `/task_list` 合并同文件两次读 + 用上 `orjson`

- **依赖**：无（**修订**：原写「依赖 ticket 01 的计数器约定」——本 ticket 不引入缓存，也不依赖注册表）
- **关联**：spec 014 §12.4（修订）、决策 6；§接口草案「改造：任务状态读写」
- **状态**：resolved 2026-10-14
- **⚠️ 2026-10-14 修订**：**范围不变（合并两次读），但新增一条：用上已装的 `orjson`**。审核确认这里是**全 spec 唯一真正的重解析场景**（平均 55.9KB / 中位 18.1KB），orjson 的 2–5 倍加速在这里成立——与状态文件（216B）形成鲜明对比。

## 目标

把 `GET /api/task_list` 每行对**同一份结果文件**的两次读合并为一次，并把它 98% 的耗时拿掉。

## 背景

基线拆解（`baseline-result.json` → `task_list_breakdown`）：

- `GET /api/task_list` p50 = **78.09ms**（p95 79.03ms）
- 其中纯 SQL（`list_video_tasks()`）只有 **2.9ms**
- 每行文件读（`_task_title_from_file` + `_task_has_note`）**151.4ms**，**1.03 open/行**
- 整个请求 `stat` 计数 1183.6

**文件有多大**（实测 `backend/note_results/`）：873 个结果文件共 **47.6MB**，平均 **55.9KB**、中位 **18.1KB**。所以这是**真·大文件重复解析**——本 spec 里收益最实的一处。

两个函数读的是**完全相同的文件**、做**完全相同的解析**：

- `_task_title_from_file(task_id)`（`backend/app/routers/note.py:1904-1918`）：`Path(NOTE_OUTPUT_DIR)/f"{task_id}.json"`、`is_file()`、`read_text()`、`json.loads()`，返回 `_result_title(result)`；**读失败返回 `""`**。
- `_task_has_note(task_id)`（`backend/app/routers/note.py:1921-1931`）：**再次**做 `is_file()` + `read_text()` + `json.loads()`；判定是 **`markdown` 是字符串且 `.strip()` 非空**（不是「文件存在」）；读失败返回 `False`。

并且 `list_video_tasks()`（`backend/app/db/video_task_dao.py:87`）是**无 LIMIT 的全表读**，其 docstring 自述「任务攒到几千行时每次都是全表读 + 全量序列化」。

**这是本 spec 里唯一一处「先修结构、再谈缓存」的改动**——缓存一个每行读两遍的实现，收益上限只有一半。

## 改动点

1. 在 `backend/app/routers/note.py` 新增合并读函数：

   ```python
   def _read_result_summary(task_id: str) -> tuple[str, bool]:
       """一次读盘同时得出 title 与 has_note。文件缺失/损坏 → ("", False)。"""
   ```

   - 内部只做一次 `Path(...).is_file()` + 一次 `read_text()` + **一次 `orjson.loads()`**。
   - 复用既有 `_result_title(result)` 提取标题；`has_note` 严格沿用原语义：**`markdown` 是 `str` 且 `.strip()` 非空**。
   - **失败态不能混淆**：`title` 失败是 `""`、`has_note` 失败是 `False`——两者都失败时返回 `("", False)`，与分别调用两个旧函数的结果一致。
2. **用上 `orjson`**（`orjson==3.10.16` 已在 `backend/requirements.txt` 且**已装在 venv**，但全仓**零处使用**）：
   - `import orjson` 后改用 `orjson.loads(bytes)`。注意 `orjson.loads` 接受 `bytes`/`str`/`bytearray`，**不接受文件对象**；建议 `result_path.read_bytes()`（省一次解码）。
   - **零新增依赖**，不需要改 `requirements.txt`。
   - `orjson.loads` 对非法 JSON 抛 `orjson.JSONDecodeError`（`json.JSONDecodeError` 的子类，但**不要依赖这一点**），异常处理要照旧捕获 `Exception`。
   - **范围限制**：只改本 ticket 涉及的读路径。**不要**顺手把全仓 `json.loads` 都换掉——`_read_task_status`、`_update_status` 那些路径读的是 216B 小文件，换 orjson 收益可忽略而改动面很大。
3. `list_tasks()`（`backend/app/routers/note.py:1934-1973`）改为遍历时调用一次合并函数，把两处调用点（`_task_title_from_file(task_id)` 与 `_task_has_note(task_id)`）替换掉。
4. `_task_title_from_file` / `_task_has_note` 若在别处仍有调用方，保留为薄封装（内部调合并函数），避免改动面外溢——**先 grep 确认调用点**。
5. `_freeze_result` 之类的结果内容映射保持不变；返回体 `{"tasks": [...], "total": len(tasks)}` 结构不变。
6. 本 ticket **不引入缓存**：`/task_list` 有「新建任务后列表必须立刻出现」的既有承诺（入队即落库，`backend/app/routers/note.py:902` `_enqueue_task`），缓存它的风险高于收益。

## 验收

- `GET /api/task_list` 在 N=200 时 p50 从 **78.09ms** 显著下降。
- 每行文件读从 **1.03 open/行** 降到 **≤0.5 open/行**（即每行至多一次读）；`stat` 计数同比例下降。
- 返回的 `tasks[]` 每个字段与改动前**逐字段一致**（用基线脚本抓前后响应做 diff，而不是只看总数）。
- 空文件 / 损坏 JSON / 文件缺失三种边界下的 `title` 与 `has_note` 与改动前一致。
- 新建任务后立刻调 `/task_list` 能立刻看到该任务（既有承诺不被打破）。
- **`orjson` 收益单独可测**：同一批文件用 `json.loads` vs `orjson.loads` 各解析一遍，给出倍数（用于报告里区分「合并读」与「换解析器」各自的贡献）。

## 测试

- `test_task_list_single_read.py`：
  - N=200 时用 monkeypatch 计数 `open`/`stat`，断言每行至多一次文件读（**以 `stat` 为准**，`app/` 有 Cython 产物，`open` 计数偏低）；
  - 空文件、损坏 JSON、文件缺失三种边界下 `(title, has_note)` 与旧实现逐字段一致（同一 fixture 同时调新旧实现做对比断言）；
  - **`orjson` 与标准库解析同一 fixture 的结果必须相等**（防 `orjson` 对某些边界输入的行为差异，如大整数、`NaN`、重复键）；
  - `total` 与 `tasks` 长度一致。
- 回归：全量 `pytest` 不低于 653 passed（`specs/013-local-transcriber-hardware-acceleration/spec.md:65`）。

---

## Comments

### 实施记录（2026-10-14）

| 位置 | 改动 |
| --- | --- |
| `backend/app/routers/note.py:1952` | 新增 `_loads_result(raw: bytes)` —— `orjson` 优先、标准库 `json` 兜底 |
| `backend/app/routers/note.py:1977` | 新增 `_read_result_summary(task_id) -> tuple` —— 一次 `is_file()` + 一次 `read_bytes()` + 一次解析 |
| `backend/app/routers/note.py:2014` / `:2026` | `_task_title_from_file` / `_task_has_note` 改为薄封装（内部调合并函数），调用面零外溢 |
| `backend/app/routers/note.py:2058` | `list_tasks()` 每个 task_id 只调一次 `_read_result_summary` |
| `backend/tests/014-backend-cache-optimization/test_task_list_single_read.py` | 新增 **28 用例** |
| `backend/tests/014-backend-cache-optimization/baseline_measure.py` | 新增 `merged_read_p50_ms` / `stat_calls_per_row` / `merged_stat_calls_per_row` 与 `measure_orjson_benefit`（`--orjson-files`，默认 200） |

`backend/requirements.txt` **未改**（`orjson==3.10.16` 早已 pinned 且装好）。

### ⚠️ orjson 与标准库的**真实差异**（实测，ticket 原文写错了一条）

TDD 过程中被用例当场抓出来的两条，都已写进 `_loads_result` 的 docstring 并由用例锁定：

1. **裸 `NaN` / `Infinity`：orjson 拒收，标准库收下。**
   结果文件是 `save_note_to_file`（`backend/app/routers/note.py:767-772`）用
   `json.dump(asdict(note), f, ensure_ascii=False, indent=2)` 写的 —— 标准库默认
   `allow_nan=True`，所以裸 `NaN` 是**合法输出**。只换解析器不兜底，这些文件会解析失败，
   表现为「标题丢了、笔记标记没了」的**静默降级**。**这就是必须有标准库兜底的原因。**
2. **超出 64 位的整数：orjson 把它降级成 `float`（丢精度），标准库保留精确 `int`。**
   实测 `123456789012345678901234567890` → orjson 给 `1.2345678901234568e+29`，
   **不抛异常**。
   ⚠️ **ticket 原文写的「大整数会抛」是错的** —— 它不抛，它悄悄改类型。这里只取
   `markdown` 与 `audio_meta.title` 两个字符串字段，所以对 `/task_list` 无影响，但已用
   `test_orjson_downgrades_huge_integers_but_extraction_is_unaffected` 记录在案。

（第三处差异 —— UTF-16 输入：`json.loads(bytes)` 会自动嗅探编码而 `read_text(encoding="utf-8")`
不会。兜底分支显式 `raw.decode("utf-8")`，避免悄悄放宽旧语义。）

### 顺手修掉的一个真 bug

`_read_result_summary` 对「合法 JSON 但不是对象」（例如文件内容为 `[1,2,3]`）退化为
`("", False)`。**原实现会在这里炸**：旧 `_task_title_from_file` 的 `result.get("audio_meta")`
在 `try` 之外，抛 `AttributeError` → 顺着 `list_tasks` 的外层 `except Exception`
（`backend/app/routers/note.py:2074-2076`）把**整个列表接口**打成 500。一个坏文件毁掉全表。
用例：`test_non_dict_result_degrades_instead_of_breaking_the_list`。

### ⚠️ 验收口径偏差：`open/行` 在主口径里不再可用

ticket 验收写「每行文件读从 1.03 open/行 降到 ≤0.5 open/行」。实施后这个数**失去了意义**：
薄封装走 `Path.read_bytes()`，它绕过 `builtins.open` 的计数钩子（本来就因 `app/` 下的
Cython 产物而偏低），实测掉到 **0.02–0.05 open/行** —— 不是真的少读了，是计数看不见了。

**主判据改为 `stat/行`**（与 conftest.py 写死的口径一致），并已把它加进测量脚本：

| 指标（N=200，缓存关） | 改动前（两次读） | 改动后（合并一次读） |
| --- | --- | --- |
| 每行文件读耗时 | **112.56ms** | **56.72ms**（2.0×） |
| `stat`/行 | **8.36** | **4.25**（2.0×） |
| `GET /task_list` p50 | **162.27ms** | **67.87ms**（2.4×） |

缓存开的一组（同一命令）：每行文件读 118.93ms → 57.87ms、`stat`/行 9.21 → 4.23、
`GET /task_list` p50 196.61ms → 80.47ms。

### orjson 的独立贡献（单独可测，ticket 验收要求）

`measure_orjson_benefit` 用**真实结果文件**（`backend/note_results/`，刻意不用造的样例）
在同一份 bytes 上只比「解析」：

```
orjson 微基准（真实结果文件 200 个 / 16.6MB，中位 32176B）: json=157.52ms orjson=56.48ms → 2.79×
```

即：`/task_list` 的提速里，**合并两次读 ≈ 2.0×**，**换解析器再 ≈ 2.8×**（两者相乘 ≈ 5.6×，
与「每行文件读 112.56ms → 56.72ms」之外的其余收益一起解释 p50 的 2.4×——`/task_list` 里
还有 2.8ms 的 SQL 与框架开销不随本 ticket 变化）。

### 证据

- `backend/tests/014-backend-cache-optimization`：**28 passed**（本 ticket）；全量回归
  **727 passed, 5 warnings, 13 subtests passed**（历史基线 653，无退化）。
- pyright：`backend/app/routers/note.py` **仍为 14 errors —— 与改动前逐条同位置**
  （全部落在 1029/1030/1031/1159/1165/1213/1236/1652/2113 等未改动行上，属仓库既有类型
  宽松问题）；`backend/tests/014-backend-cache-optimization/*` **0 errors**。ruff：全部 clean。
- 语义等价：`_EDGE_CASES` 13 种形态（缺失 / 空文件 / 截断 JSON / `markdown` 为空白或
  非字符串或 null / `audio_meta` 缺失或 null 或非 dict / `title` 为数字或空白 / 空对象）
  逐个与**逐字抄下来的旧实现**对比 `(title, has_note)`。
- 调用面：grep 确认 `_task_title_from_file` / `_task_has_note` 的唯一调用点是
  `list_tasks()`（`backend/app/routers/note.py:2068-2069` 改动前），所以保留薄封装即可，
  没有其它调用方需要改。

### 给后续 ticket 的输入

`orjson` 的适用范围就此打住：状态文件 216B，`_read_task_status` / `_update_status` /
`task_cleanup.py` 等路径**一律不动**（换过去只是多一条依赖路径、零收益）。

## Answer

**已完成**：`/task_list` 每行对同一份结果文件的两次读合并为一次
（`_read_result_summary`，`backend/app/routers/note.py:1977`），解析换用已在依赖里的
`orjson` 并保留标准库兜底（`_loads_result`，`:1952`）。实测 `stat`/行 **8.36 → 4.25**、
每行文件读 **112.56ms → 56.72ms**、`GET /task_list` p50 **162.27ms → 67.87ms**；
orjson 单独贡献 **2.79×**。

**两条偏差**：① 验收主口径从 `open/行`（实施后因 `read_bytes` 绕过计数钩子而失真）改为
`stat/行`；② 兜底不是可选项 —— orjson 拒收标准库 `json.dump` 会写出的裸 `NaN`/`Infinity`，
少了兜底就是静默降级。**顺手修掉**「非对象结果文件会把整个列表接口打成 500」的真 bug。

