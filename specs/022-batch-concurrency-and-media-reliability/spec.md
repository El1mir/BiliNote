# 022 · 批量生成并发与媒体/OCR/判定/ASR 可靠性

状态：draft · 创建：2026-11-12 · 来源：父任务 T-078
关联：spec 009（真并发 / 重启恢复）、spec 012（429 停放）、spec 007（媒体资源）、
spec 008（OCR 辅助与画面判定）、spec 003（OpenAI 兼容 ASR）

## 1. 背景与现象

2026-11-12 用 run.bat 跑 193 条新视频的合集/合并任务，日志与耗时暴露六类问题：

- 合并任务逐条串行：s1 完成 12:36:45 才启动 s2，s2 12:54:55 才启动 s3，s3 13:05:28、s4 13:17:16。
  同一时刻只有 1 条子视频在跑，193 条总时长线性叠加。
- 普通批量隐藏 5 并发上限：设置并行 8，实际最多 5 条在跑。
- 媒体登记全部失败：`无法登记任务媒体资源`，ValueError 指向 `backend/data/BV....mp3`
  不在 `backend/data/data` 之下。
- OCR 429 无重试：s2 一轮 30 张里 26 张失败，日志 `OCR 调用失败（HTTP 429）`。
- 画面判定空结果触发整任务重试：`画面价值判定失败：判定结果里找不到帧列表`。
- ASR 序列化告警：Pydantic serializer warning，`Expected int ... input_value='0'`。

用户判断「批量生成没有完全并行」成立，且不止一处。

## 2. 根因（R1–R6）

### R1 合并任务内部逐条串行

`backend/app/routers/note.py:1406-1531` 的 `_run_merged_note_task`：第 1453 行
`for index, raw in enumerate(items, start=1)`；第 1501 行
`note = _execute_note_with_retry(sub_task_id, generator, _execute)` 在循环内逐条等待。
第 1432-1437 行 docstring 明确写「逐条串行而不是并发」，理由是保持章节顺序、避免一条任务
吃掉 N 个槽位。`run_note_task` 在 1265-1293 行直接分叉到合并流程，合并任务本身不占外层
闸门；每个子项各自过闸门。因此单条合并任务的并发恒为 1。分发池（`note.py:314-402`）
只并发「多条独立任务」，一个合并任务只是一个任务。

### R2 普通批量有效并发是 5，不是设置值

`backend/app/services/task_serial_executor.py:9-15`：线程池 `max_workers` 取
`TASK_MAX_WORKERS`，默认 5，构造期固定；`run()` 里 `future.result()` 同步阻塞调用线程。
`backend/app/routers/note.py:737-751` 的 `_run_with_parallel_gate`：先拿 gate 名额
（上限 8），再 `task_serial_executor.run()`。实际并发 = min(8, 5) = 5，用户设置 6/7/8
全部无效；分发池 8 个线程里还有 3 个占着 gate 名额空等内层池。

### R3 媒体资源登记全部失败：数据根多拼一层 data

`backend/app/utils/path_helper.py:8-18`：开发态 `base_dir = <backend>/data`，第 16 行再
`os.path.join(base_dir, "data")`，返回 `<backend>/data/data`。

下载落盘在 `backend/app/services/note.py:1194/2026/2052/2110` 的
`os.getenv("DATA_DIR", "data")`，即 `<backend>/data`。`media_resource_service.py:70-81`
的 `_roots()` 用 `get_data_dir()` 做 video/audio 根，`register_resource` →
`_managed_relative`（156-177）直接抛越界；调用方 `services/note.py:1949` 捕获后只打日志。

后果：媒体登记表永远为空，保留期清理和容量统计看不见这些文件；`backend/data` 里遗留
`BV*.mp3`。`backend/data/data` 当前为空，可安全修正。

### R4 OCR 429 无重试、无全局并发闸门

`backend/app/services/note.py:1304-1439` 的 `_run_ocr_stage`：按
`ocr_stage_concurrency`（默认 4，用户可调到 8）起线程池逐张 OCR；单张失败被
1393-1400 捕获后只计数，图照插、任务照跑。

`backend/app/services/ocr_client.py:569-674` 的 `recognize_image` 是单次 requests 调用，
429 直接 `_http_error` 抛 `OcrError`；`_is_non_retryable`（114-124）只排除认证/配置类，
429 被标记为「可重试」却没有任何重试循环。多任务叠加时并发可达 8×8，触发上游限流。

### R5 判定空结果被当硬异常，触发整条任务重试

`backend/app/gpt/universal_gpt.py:307-312`：所有批次都解析不出条目时抛
`WorthJudgementError("判定结果里找不到帧列表…")`；`backend/app/services/note.py:1127-1137`
捕获后 `_handle_exception` 并 raise，触发整个任务级重试（重新下载/转写/总结）。

而提示词 `universal_gpt.py:809-810` 明确允许模型返回 `{"frames": []}`，两者语义冲突。

### R6 ASR Pydantic 序列化警告

`backend/app/transcriber/openai_asr.py:597-608` 的 `_to_dict` 对 OpenAI SDK 转写对象调
`model_dump()`。兼容服务把 `segments[].id/seek` 返回成字符串 `'0'`，SDK 模型未校验就持有
str，Pydantic 序列化告警 `Expected int ... input_value='0'`。仅噪音，但会淹没真实日志。

## 3. 目标与非目标

目标：

1. 用户设置的「最大笔记并行任务数」等于实际同时生成的视频数，不再有隐藏的 5 上限。
2. 合集/合并任务内部并行生成，最终章节顺序严格等于用户勾选顺序。
3. 合并任务遇到 429 停放或进程重启后，已完成的子项不重新生成。
4. 媒体资源登记使用真实数据根，重启后自动回填遗留文件。
5. OCR 429 有退避重试与进程级并发上限，持续失败不拖垮整条任务。
6. 画面判定空结果/解析失败降级为「保留全部候选」，不再触发整条任务重试。
7. 消除 ASR 的 Pydantic 序列化告警。

非目标：

- 不改前端 UI 视觉、不改 Tauri 移除成果、不改后端公开 API 形状。
- 不改供应商配额，不实现跨进程分布式调度。
- 不把每一条视频内部的处理阶段（下载/转写/总结）再拆成并行；本次只并行「多条视频」。
- 不为 193 条任务做断点续传之外的通用作业系统。

## 4. 已定决策

| 编号 | 决策 | 理由 |
|---|---|---|
| D1 | 单一调度器：`_run_with_parallel_gate` 在 gate 内直接执行 `execute_fn`，删除 `task_serial_executor` 的嵌套线程池。gate 是唯一并发上限；分发池保持 `MAX_PARALLEL_NOTES_LIMIT`（8）。单条任务经 BackgroundTasks 执行时同样只受 gate 约束 | 消除 min(gate, 5) 的隐藏上限；线程数不再与设置脱节。用户设置随改随生效 |
| D2 | 合并任务扇出：读当前 gate.limit 作为子任务并发数（最多等于 items 数），每个子项各自过 gate；结果按 index 排序后合并；进度用完成计数 | 全局在途视频数仍不超过 gate；章节顺序由排序保证，不靠串行 |
| D3 | 合并任务断点：每完成一条子项，原子写 `checkpoints/<task_id>.merge/<index>.json`（url、markdown、title、duration、video_id、cover_url、transcript、source_url）。重启或 429 停放后加载并跳过校验通过的已完成项；最终合并成功后删除该目录；失败项不写 checkpoint，恢复时重试 | 193 条长任务不能因一条 429 从头再来；checkpoint 是「已完成的事实」，不是缓存 |
| D4 | 数据根：`get_data_dir()` 统一为「`DATA_DIR` 环境变量相对 backend 解析；未设置时 `<backend>/data`；冻结态 `<exe_dir>/data`」，不再二次拼 data。保留期/回填/下载/磁盘检查全部走同一根 | 下载与登记必须看同一个目录；二次拼 data 是 R3 直接原因 |
| D5 | OCR：`recognize_image` 内最多 3 次重试，只重试 429/5xx/超时；429 优先读 `Retry-After`，指数退避 0.5/1/2 秒加抖动，单次等待封顶 30 秒；进程级 `BoundedSemaphore` 上限 `OCR_MAX_CONCURRENCY`（默认 4），所有任务共享。per-task worker 数取 min(设置值, 全局上限)。持续 429 仍按单张失败跳过，任务不失败，但只打一条聚合告警 | 429 是配额节流不是配置错误；全局闸门防 8×8 叠加 |
| D6 | 判定降级：`judge_note_frames` 在所有批次都没有条目时不再抛 `WorthJudgementError`，而是返回「全部候选保留」的 degraded 结果；显式 `{"frames": []}` 同样降级（避免静默零插图）；网络/鉴权等真正的 API 错误仍抛出；降级写入任务 detail 与日志 | 判定是「挑图」不是「生成」；挑不出图不该让整条任务重新下载/转写 |
| D7 | ASR：`_to_dict` 调 `model_dump` 时传 `warnings=False`，并优先使用已经就是 dict 的原始响应；不改变 transcript 数值解析 | 告警来自兼容服务的字符串 id/seek；序列化层静音即可，不动数据 |

## 5. 待确认问题（Q1–Q4，等用户拍板）

- **Q1 合并扇出默认值**：直接等于 gate（用户设 8 就 8 路），还是额外封顶 4？
  推荐等于 gate，由用户用设置自行降级；8 路 fast-whisper/ffmpeg 对 CPU/内存压力大。
- **Q2 显式 `{"frames": []}` 的语义**：推荐按 D6 降级为「全部候选保留」；若要保留
  「模型明确判定无画面就不插图」，需要模型返回可区分字段，否则无法与解析失败区分。
- **Q3 OCR 全局上限默认 4 是否合适**：用户设置 8 时，是钳制到 4，还是允许设置覆盖全局上限？
- **Q4 checkpoint 放在 note_output 下是否纳入现有保留期清理**：建议合并成功后立即删，
  异常退出时保留到任务终态。

## 6. 接口与数据结构草案

### 6.1 调度

```python
def _run_with_parallel_gate(execute_fn):
    gate = _get_parallel_gate()
    with gate:
        return execute_fn()          # 不再经 task_serial_executor.run
```

- `task_serial_executor` 模块保留导出名做兼容（别处可能 import），但 note 路由不再依赖它；
  若全仓无引用则删除模块与其测试（W1 内决定，不晚于 W1 收尾）。
- `_ParallelGate.limit` 作为并发事实来源；合并扇出直接读它。

### 6.2 合并 checkpoint

路径：`<NOTE_OUTPUT_DIR>/checkpoints/<task_id>.merge/<index>.json`（index 从 1 起）。

```json
{
  "version": 1,
  "index": 1,
  "url": "https://www.bilibili.com/video/BV...",
  "title": "章节标题",
  "markdown": "...",
  "duration": 123.0,
  "video_id": "BV...",
  "cover_url": "...",
  "transcript": {"segments": []},
  "source_url": "..."
}
```

- 写入：`tmp + os.replace` 原子替换；`version` 不匹配视为失效。
- 读取：`url` 与当前 item 的 url 必须一致，否则忽略并重算。
- 清理：合并成功（任务终态 SUCCESS）后删除整个 `<task_id>.merge` 目录；
  任务失败/停放时保留，供下一次恢复。

### 6.3 OCR

```python
OCR_MAX_RETRY = 3                       # 首次 + 2 次重试
OCR_BACKOFF_BASE = 0.5                  # 0.5 / 1 / 2 秒 + 抖动
OCR_RETRY_AFTER_CAP = 30.0              # 单次等待上限
OCR_MAX_CONCURRENCY = int(os.getenv("OCR_MAX_CONCURRENCY", "4"))
_OCR_GLOBAL_SEM = BoundedSemaphore(OCR_MAX_CONCURRENCY)   # 进程级
```

`recognize_image` 返回成功/抛 `OcrError`；重试耗尽后 `OcrError.rate_limited=True`
（或保留 status_code=429 判定）供调用方聚合告警。

### 6.4 判定降级

`JudgementOutcome` 增加 `degraded: bool = False` 与 `degraded_reason: str | None`。
`judge_note_frames` 返回 degraded 结果时，`approved` 为全部候选（受 `note_max_images` 限制）。
任务 detail 写 `{"judgement_degraded": true, "judgement_degraded_reason": "..."}`。

### 6.5 数据根

```
DATA_DIR 未设置        → <backend>/data          （开发）/ <exe_dir>/data（冻结）
DATA_DIR 相对路径      → 相对 <backend> 解析（开发）/ 相对 <exe_dir>（冻结）
DATA_DIR 绝对路径      → 原样使用
```

`get_data_dir()` 只创建并返回上述目录，不再追加 `data`。 启动日志打印解析后的 data_root；
若 `<backend>/data/data` 仍存在且非空，打 warning（不自动删）。

## 7. 流程

### 7.1 普通批量

用户提交 N 条（含分发池）→ 每条任务经 `_run_with_parallel_gate` 拿 gate 名额 →
直接在当前线程执行 `execute_fn`（不再二次进池）→ 在途数 = min(gate.limit, N)。
设置改大改小在下次进闸时生效。

### 7.2 合并任务扇出

1. `_run_merged_note_task` 读 `gate.limit`，`workers = min(limit, len(items))`。
2. 加载已有 checkpoint，命中且校验通过的项直接复用（不调用生成）。
3. `ThreadPoolExecutor(max_workers=workers)`，按 index 提交未完成项；每项内部仍
   `with gate:` 才真正跑，因此全局在途不超过 gate。
4. 完成计数 + 锁更新状态：`合并生成 {done}/{total}`，进度 = done/total*90。
5. 任一子项返回 `RATE_LIMIT_PARKED`：停止提交新项、取消未开始项、等在途项结束、
   落盘 checkpoint，再按 spec 012 的停放逻辑交还队列。
6. 全部完成后按 index 排序 entries（failures 保留原位说明），合并 Markdown，清理 checkpoint 目录。

### 7.3 OCR 阶段

`_run_ocr_stage` 计算 `workers = min(设置值, OCR_MAX_CONCURRENCY, total)`；
每次 `recognize_image` 在全局 semaphore 内执行重试；
统计 attempts/retries/rate_limited；持续失败只打一条聚合 warning，单图缺失不失败任务。

### 7.4 判定阶段

`_judge_note_frames` 调 `judge_note_frames`；degraded 结果照常进入挑图层（全候选），
写 detail 标记与一条 warning；网络/鉴权异常仍走原有失败/重试路径。

## 8. 测试要点与工作包验收

统一测试根：`backend/tests/022-batch-concurrency-and-media-reliability/`（按 W 分 `w1/`…`w5/`）。
命令统一用 `backend/.venv/Scripts/python.exe -m pytest <path> -q`（Windows）。

| 包 | 范围 | 验收命令 | 证据格式 |
|---|---|---|---|
| W0 | spec + README 索引 | `git diff --check`；人工核对 6 段齐全、索引行存在 | 本文件 + `specs/README.md` 行号 |
| W1 | note.py gate/合并/断点、task_serial_executor.py、tests/009 test_parallel_scheduler.py、tests/test_task_serial_executor.py | `pytest tests/022.../w1 tests/009.../test_parallel_scheduler.py tests/test_task_serial_executor.py -q` | pytest 摘要；最大在途计数断言；checkpoint 文件列表；章节顺序断言 |
| W2 | path_helper.py、media_resource_service.py、init_db.py | `pytest tests/022.../w2 tests/007.../test_media_resources.py -q` | 临时 DATA_DIR 下 media_resources.path；`_roots()` 断言；init_db 回填计数；日志无登记失败 |
| W3 | ocr_client.py、note.py `_run_ocr_stage`/`_judge_note_frames`、universal_gpt.py、ocr_assist.py | `pytest tests/022.../w3 -q` + 既有 008 相关用例 | 429→200 请求次数；12 路并发最大在途；degraded detail；聚合告警条数 |
| W4 | openai_asr.py | `pytest tests/022.../w4 -q` | `warnings.catch_warnings(record=True)` 断言无 Pydantic 告警；时间轴断言 |
| W5 | 集成 | 上述全量 + 真实 3–5 条短视频合并 | 日志片段（并发>1、顺序、无五类报错）；任务结果 Markdown |

### 分条测试要点

1. **并发上限**：10 个假任务，gate=8 时峰值 8；gate=3 时峰值 3；无 5 的隐藏上限。
2. **合并扇出与顺序**：10 条、gate=4，峰值 4；最终章节顺序 1..10；进度单调至 10/10。
3. **合并断点**：第 5 条模拟 429；1–4 落 checkpoint；恢复后生成计数只覆盖 5–10；
   最终 10 条齐全；成功清理 checkpoint。
4. **媒体根**：临时 DATA_DIR 生成 mp3 → register_resource 成功、path 为 `audio:<相对路径>`；
   `_roots()["audio"] == 解析后的 DATA_DIR`；重启式 init_db 回填已有文件；
   日志无 `无法登记任务媒体资源`。
5. **OCR**：mock 429（带 Retry-After: 1）→ 200，请求 2 次成功；12 路并发全局上限 4；
   持续 429 时任务完成、失败计数正确、仅一条聚合告警、图片仍插入。
6. **判定降级**：`{"frames": []}` 与垃圾 JSON 均不抛异常；approved == 候选（受上限）；
   任务 detail 有 `judgement_degraded=true`；网络错误仍抛。
7. **ASR**：字符串 id/seek 的假 SDK 模型，无 `PydanticSerializationUnexpectedValue`；
   transcript 时间轴解析仍正确。
8. **回归**：`tests/022...`、`tests/009.../test_parallel_scheduler.py`、
   `tests/007.../test_media_resources.py` 全绿；既有 008 判定用例按新语义更新
   （显式空清单从「抛异常」改为「degraded」）。
9. **真实合并**：3–5 条短视频合并任务，日志显示子项并发 >1、章节顺序正确、
   无媒体登记/ASR 告警/OCR 429/判定失败五类报错。

## 9. 验收映射（卡面 9 条 → 工作包）

| 卡面验收 | 工作包 | 测试位置 |
|---|---|---|
| 1 设置 8→峰值 8、3→峰值 3 | W1 | w1/test_parallel_gate.py |
| 2 合并 gate=4 峰值 4、顺序、进度 | W1 | w1/test_merge_fanout.py |
| 3 合并第 5 条 429 断点续跑 | W1 | w1/test_merge_checkpoint.py |
| 4 临时 DATA_DIR 登记/回填/日志 | W2 | w2/test_data_root.py |
| 5 OCR 429 重试/全局 4/聚合告警 | W3 | w3/test_ocr_retry.py |
| 6 判定空结果降级 | W3 | w3/test_judge_degrade.py |
| 7 ASR 字符串 id/seek 无告警 | W4 | w4/test_asr_serialization.py |
| 8 三个测试路径全绿 | W1–W4 | 见上表命令 |
| 9 真实 3–5 条合并日志 | W5 | w5/evidence.md + 日志 |

## 10. 风险与回滚

- **并发升高带来的资源压力**：gate 是唯一上限，用户可下调；默认值不变（仍是设置值）。
  Q1 决定是否给合并扇出额外封顶。
- **checkpoint 占盘**：每条子项一份 Markdown+transcript；成功即删，失败保留到终态。
  Q4 决定是否纳入保留期清理。
- **调度改造影响既有并发语义**：spec 009 的测试会从「min(gate, 池, executor)」改为
  「gate 即上限」；回滚方式是恢复 `task_serial_executor.run` 包装与旧断言（单提交可逆）。
- **判定降级改变 008 的失败语义**：显式空清单不再让任务失败；网络错误路径不动。
  回滚只需恢复 raise 分支与 008 测试。
- **数据根变更**：若用户曾把 `DATA_DIR` 指向 `data/data`，迁移后会指向 `data`；
  W2 启动时对旧 `data/data` 打 warning 并保留文件，不自动搬运。

## 11. 实现清单

- [ ] W0 spec 与索引（本文件）
- [x] W1 调度器收敛 + 合并扇出 + checkpoint + 判定降级
  （`backend/tests/022-batch-concurrency-and-media-reliability/w1/`：parallel_gate / merge_fanout / merge_checkpoint / judge_degrade）
- [ ] W2 数据根修复与遗留回填
- [ ] W3 OCR 重试/全局闸门 + 判定降级
- [ ] W4 ASR 序列化告警
- [ ] W5 集成验收与真实合并日志
