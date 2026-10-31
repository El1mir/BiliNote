# 004 后端流水线重复工作与缓存接缝

- 类型：架构决策
- 状态：implemented（缓存接缝、OCR 并行、跨任务共享转写、阶段入口单次读盘、音频缓存合并均已落地；OCR_STAGE_CONCURRENCY 默认值待 ticket 003 基线定稿）
- 依赖：无
- 阻塞：后端流水线实现（并行化、跨任务复用）
- 关联规格：specs/017-web-rebuild-and-architecture/spec.md 第 4、8 节
- 设计范围：只定义流水线内部的重复工作、缓存归属与并行边界；不改变笔记语义、不改变任务状态协议（那属于 ticket 002）。

## 1. 目标与删除测试

生成链路把「下载 → 字幕/转写 → 抽帧判定 → OCR → LLM 分段 → 插图 → 落盘」写在同一个 2278 行的 `NoteGenerator` 里，每个阶段自己管缓存文件、自己读盘、自己拼状态。结果是同一份转写缓存被三处各读一遍，且读法不一致：

- `note.py:371` 与 `note.py:1867` 用 `data.get("language")`，缺字段容忍；
- `note.py:1936` 用 `data["language"]`，缺字段直接 KeyError，把任务打断。

同一个缓存文件，先被哪个阶段读到决定了任务是继续还是崩 —— 这不是策略，是巧合。

删除测试：把音频元信息、转写结果、画面判定/OCR 三类缓存的读写各收成一条缝之后，流水线里不应再出现裸的 `json.loads(...read_text(...))`；如果删掉新接缝会让复杂度回到各阶段，而不是减少，就先不迁移。

## 2. 已落地的接缝（本次实现）

新增 `backend/app/services/note_cache.py`，一条策略：**坏缓存是 miss，不是任务失败**。

- `read_json_cache(path) -> Optional[dict]`：文件不存在、JSON 坏了、顶层不是对象，一律返回 `None`。
- `write_json_cache(path, payload) -> bool`：先写同目录临时文件再 `os.replace`，半截 JSON 不会被下一个任务读到；`ensure_ascii=False` 保持中文可读；写失败只告警，不影响任务结果。
- `read_transcript_cache(path) -> Optional[TranscriptResult]`：缺 `full_text` 视为 miss；单段无法解析只跳过该段并告警，不作废整份缓存。
- `write_transcript_cache(path, transcript)` / `read_audio_cache(path, require_file=True)` / `write_audio_cache(path, audio)`。
- `read_audio_cache` 默认校验缓存里记的媒体文件仍在：媒体清理会按容量/过期删音频，只认缓存不认文件会让任务拿着死路径去转写，报出误导性的 `No such file or directory`。

`NoteGenerator` 侧的迁移：`note.py` 的 5 处缓存写入（2 处音频、3 处转写）与 4 处读取全部改走接缝；`note.py:735` 的 OCR 缓存读取保留原样（它有「本次是否开了 OCR」的额外语义，属于后续工作）。

## 3. 仍未处理的重复工作（设计，按收益排序）

### 3.1 跨任务复用：同一视频重复生成

**已实现（2026-10-17），范围比原设计窄：只共享转写结果，不共享音频。**

原设计想共享 `audio.json` + `transcript.json` 两份，落地时收窄到转写一份，理由：音频缓存里存的是**绝对文件路径**，而媒体清理会按容量/过期删音频；把音频条目共享出去，等于让 A 任务的清理动作打穿 B 任务的缓存（`read_audio_cache(require_file=True)` 只能把这种失效降级成 miss，不能阻止它发生）。转写结果是纯数据、没有外部引用，可以安全共享。

键 = `sha256("{video_url}|{transcriber_key}")[:16]`，落在 `NOTE_OUTPUT_DIR/shared/transcript_{key}.json`：

- `shared_transcript_path(base_dir, video_url, engine_key)` 定义在 `backend/app/services/note_cache.py`（纯函数、无重依赖，因此可单测）；
- `_transcriber_key()`（`backend/app/services/note.py`）拼出引擎身份：`transcriber_type` + `model_size`（whisper 家族）+ `openai_asr_id`（openai-asr 时取 `TranscriberConfigManager().get_active_openai_asr()` 的 id，取不到用 `unconfigured`）。

**换引擎必须换键**：同一段音频在不同 ASR 引擎/模型下本来就该得出不同文本，只按视频 ID 复用等于把上一次的答案冒充这一次的结果。

接线位置两处：

- `run()` 的**下载之前**（`note.py`，步骤「1.5」）：命中就直接 `transcript = shared` 并回填任务级缓存。放在下载之前是关键 —— 命中意味着这个视频 + 这个引擎已经转过了，可以直接跳过音频下载与 ASR，而这两步才是整条链路里最贵的部分（`need_full_download` 随后因为 `has_transcript=True` 自动降为只取元信息）。
- `_transcribe_audio()` 内部再查一次（第二道保险，覆盖不经过 `run()` 前置检查的调用方），命中则回填任务级缓存后返回；转写成功后同时写任务级与共享两份。

命名沿用仓库里已有的先例：OCR 中间结果早就是按 `video_url` 的 sha256 短哈希做跨 task_id 缓存（`_ocr_cache_file`，`note.py:714`），注释写明「重试会换一个新的 task_id，但复用要跨 task_id 生效」。用 sha256 而非 sha1 只是为了避免静态规则告警，代价为零。

边界：共享条目与任务级缓存同在 `NOTE_OUTPUT_DIR` 下，媒体清理只处理视频/音频/截图三类资源，不碰 `shared/`。因此不会出现「清理一个任务打穿另一个任务的缓存」。共享条目目前没有独立的容量/过期策略 —— 单条转写 JSON 只有几十到几百 KB，量级不构成问题；等 ticket 003 的基线数据出来后如果确实需要，再补。

### 3.2 抽帧判定与 OCR 的并行

**已实现（2026-10-17）**，实现时修正了设计里的一处误判：

- `_judge_note_frames` 并不是「逐张图调用外部模型」。它把所有候选帧的时间点、字幕与图片 URL 一次性交给 `gpt.judge_note_frames`，是一次 LLM 调用、一次网络往返。按图并发在这里没有可并行的单位，硬拆反而会把一次上下文完整的判定切碎，破坏判定质量。结论：判定阶段不做并发，设计作废。
- `_run_ocr_stage`（`note.py:1070`）确实是逐张串行：每张先 ffmpeg 寻帧截图，再调用 OCR 服务。已改成两段：
  - 第一段串行 —— 截图（本地 ffmpeg 寻帧，多个并发会抢同一块磁盘）、`register_resource`、`_image_to_data_url`，结果按索引存进 `staged`；
  - 第二段并发 —— `ThreadPoolExecutor` + `pool.map` 识别，`map` 保序，回填顺序与串行版本一致；
  - 单张失败仍只影响该张（`_recognize` 把异常放在返回值里，由调用方计入 `failures` 并告警），不打断任务；
  - `ocr_client is None` 时退化为原地串行，不建线程池。
- 并发度常量 `OCR_STAGE_CONCURRENCY`（`note.py:111`，`max(1, _safe_int(os.getenv("OCR_STAGE_CONCURRENCY", "4"), 4))`）。限流单位仍然是它与 `max_parallel_notes` 的乘积：2 个任务 × 4 并发 = 8 个在途 OCR 请求，调这个环境变量时要一起想。
- 默认值 4 是暂定值，最终值仍待 ticket 003 的基线数据定稿。

不做：不引入新的任务队列或异步框架；`task_serial_executor.py` 的串行语义（一个任务完整跑完再跑下一个）保持不变，因为它同时是「用户能看懂进度」的保证。

### 3.3 重复读盘与重复解析

**已实现（2026-10-17）。** `_get_transcript` 与 `_transcribe_audio` 各自再读一次转写缓存，而调用方 `run()` 已经在前面读过。

做法沿用 `subtitle_attempted` 的既有模式，不引入新类型：两个阶段函数各加一个 `cache_checked: bool = False`，入口判断从 `if transcript_cache_file.exists():` 改成 `if not cache_checked and transcript_cache_file.exists():`。`run()` 调用处传 `cache_checked=True`（它刚读过同一份文件且已确认未命中），`_get_transcript` 内部 fallback 调 `_transcribe_audio` 时同样传 `True`。

语义：同一份文件刚读过且未命中，再读一遍只会多一次磁盘 IO 与一次 JSON 解析，结果不可能不同。之所以用布尔参数而不是「传入已解析对象或 miss 信号」，是因为后者要改调用方签名与返回值形状，而这里真正要删掉的只是那次多余的读盘。

### 3.4 音频缓存的双写

**已实现（2026-10-17）。**「跳过下载只取元信息」与「真实下载」两条分支写同一份缓存，且只有其中一条登记媒体资源。

新增 `_remember_audio(self, audio_cache_file, audio, task_id) -> AudioDownloadResult`（`backend/app/services/note.py`，插在 `_download_media` 之前）：内部唯一一次 `write_audio_cache`，随后在 `try/except` 里 `register_resource("audio"|"video", ...)`（逐个判 `Path(...).is_file()`），异常只记日志不影响任务，最后返回 audio。两条分支都改为调用它。

校验方式：`grep -n "write_audio_cache" backend/app/services/note.py` 只剩两处 —— import 行与 `_remember_audio` 内的调用。

## 4. 验收

- [x] 流水线里不再有裸的转写/音频缓存读写（`grep -n "transcript_cache_file.write_text\|audio_cache_file.write_text"` 为空）。
- [x] 坏缓存（截断 JSON、缺 `language`、缺 `full_text`、单段坏数据、媒体文件已删）全部按 miss 处理，任务不中断。
- [x] 缓存写入原子，不留 `.tmp` 残留文件。
- [x] `backend/tests/017-web-rebuild-and-architecture/test_note_cache.py` 覆盖上述分支；`pytest tests/017-web-rebuild-and-architecture -q` 全绿。
- [x] 3.2 OCR 阶段并发（`_run_ocr_stage` 两段式 + `OCR_STAGE_CONCURRENCY`）；判定阶段经复核为单次 LLM 调用，不需要并发。
- [x] 3.1 跨任务共享转写缓存（`shared_transcript_path` + `_transcriber_key` + `run()` 下载前查询 + `_transcribe_audio` 第二道查询）；`test_note_cache.py` 覆盖「同视频同引擎同路径 / 换引擎换视频换键 / 共享路径走同一套读写」。
- [x] 3.3 阶段入口单次读盘（`cache_checked`）。
- [x] 3.4 音频缓存双写合并（`_remember_audio`）。
- [x] `pytest tests/017-web-rebuild-and-architecture -q` = 19 passed, 1 warning。

## 5. 待确认问题

- 共享缓存的隐私边界：**已定**——共享条目只落在本机 `NOTE_OUTPUT_DIR/shared/`，与任务级缓存同一块磁盘、同一组访问权限，因此它不提供任何任务级缓存没有的可见性。多用户/多租户部署下这个前提不成立（那时需要按用户分目录），但当前部署形态是单机单用户。
- `OCR_STAGE_CONCURRENCY` 的默认值（现为 4）需要 ticket 003 的基线数据才能定稿。
- 共享转写缓存的容量/过期策略：暂不做（单条几十到几百 KB）。若 ticket 003 基线显示 `shared/` 会显著增长，再补一条独立清理规则。
