# 007 · 笔记归档导出与媒体缓存治理

- **状态**：implemented（后端验收已授权并于 2026-10-05 执行，记录见 §13；残余项见 §13.3）
- **日期**：2026-09-27
- **范围**：笔记 ZIP 导出、静态资源生命周期管理、视觉总结图像缓存与流水线耗时观测
- **上游**：002 / 005 / 006

## 1. 背景

当前前端 `MarkdownViewer` 直接把 Markdown 文本下载为 `.md`，其中截图引用的是服务端 `/static/screenshots/...` 路径；脱离当前服务端后图片会失效。截图和下载的音视频分别落在本地静态目录与 `DATA_DIR`，但数据库没有资源级过期记录，也没有设置自动保留期或手动清理能力。

视觉理解流程会将抽取帧拼成网格图，读入后编码为 base64 data URL 并发送给视觉模型。最近真实任务在“开始编码图像”后约 6 分 40 秒才落盘，但日志无法区分编码、视觉 LLM 请求和结果保存的耗时。现有临时帧/网格目录在 VideoReader 完成后清理，重试时可能重做抽帧、拼图和编码。

## 2. 目标

1. 笔记以 ZIP 形式导出，包含 `note.md` 和笔记实际引用的本地图片，离线打开时图片仍可显示。
2. 对生成的截图、下载视频和音频建立资源级数据库登记、到期时间、自动清理和手动清理能力。
3. 每个文件生成时固化 `expires_at`；修改保留期只影响之后登记的资源，不重算已有资源的到期时间。
4. 对旧版部署已经存在的受管目录文件进行一次性登记，使用各文件的文件系统修改时间作为产生时间，按资源默认保留期回填 `expires_at`；已到期资源进入清理队列。
5. 为同一任务自动重试复用已拼接网格（不跨任务复用抽帧文件），并分别记录图像准备与视觉模型请求耗时；本轮不承诺跳过抽帧或端到端加速。
6. 不减少用户设定的采样帧数，不静默降低图像质量，不改变笔记内容语义。

## 3. 非目标

- 不清理模型文件、数据库、笔记 Markdown/JSON、字幕缓存或用户配置。
- 不长期保留本来应在任务结束后删除的 ASR 切片、抽帧和网格临时文件；它们继续按任务生命周期清理。
- 不通过降低用户设置的帧数或静默降质来换速度。
- 不承诺所有视频的端到端速度必然提升；必须通过基准确认缓存命中收益和图像处理耗时。

## 4. 已定决策

| # | 决策 | 结论 |
| --- | --- | --- |
| 1 | 导出格式 | ZIP，包含 `note.md` 和 `assets/` 目录 |
| 2 | 本地图片链接 | 包内 Markdown 将已打包资源改写为相对路径 `assets/<filename>`；外部 URL 原样保留 |
| 3 | 导出图片范围 | 只打包该笔记 Markdown 实际引用且位于本服务管理目录中的图片；缺失资源须给出明确错误或可见告警，不生成悄悄缺图的归档 |
| 4 | 默认资源保留期 | 截图 7 天；视频、音频 3 天 |
| 5 | 设置语义 | 每类保留天数可配置；`0` 表示永不自动过期；允许手动清理 |
| 6 | 到期固化 | 资源登记时按当时配置写 `expires_at`；之后改设置不得重算已有记录 |
| 7 | 旧文件回填 | 首次启用时扫描受管目录中未登记的截图、视频、音频；`created_at` 取文件 `mtime`，按各类默认保留期计算 `expires_at`，已过期项可立即清理 |
| 8 | 手动清理 | 支持按资源类别清理已到期项与强制清理所选类别；强制删除须明确展示范围/数量并二次确认 |
| 9 | 缓存性能 | 缓存键必须覆盖视频内容身份、采样配置、实现版本等影响图像结果的参数；保序复用缓存结果，不减少用户选择的帧数 |
| 10 | 质量与安全 | 不静默缩小/降质图片；只打包允许根目录下的本地资源，拒绝路径穿越；ZIP 项名安全且不含绝对路径 |

## 5. 资源模型与生命周期

新增资源登记表（建议 `media_resources`），最少字段：`id`、`resource_type`（`screenshot` / `video` / `audio`）、`task_id`、`video_id`、`path`、`size_bytes`、`created_at`、`expires_at`、`deleted_at`、`last_error`。物理删除成功后删除行或写入审计字段，策略在 ticket 中明确；文件缺失时清除陈旧登记并记日志。

文件产出/下载成功后立刻登记资源。过期时间为资源产生时间加当时配置的保留天数；0 不设置到期时间。周期清理使用有界批次，先登记删除意图/记录，再删除文件并确保失败可重试；不阻塞应用启动或任务主工作线程。

升级回填必须幂等，限定扫描 `OUT_DIR` 截图、`DATA_DIR` 中可识别的视频/音频扩展名，不递归扫描其他用户数据。使用文件 mtime 近似产生时间并在回填记录标记来源为 `legacy_backfill`，便于诊断；迁移不会覆盖已有资源记录。

## 6. ZIP 导出行为

新增任务笔记 ZIP 下载 API；导出名以笔记标题安全规范化。解析 Markdown 中本地 `/static/screenshots/...` 与配置的 `IMAGE_BASE_URL` 引用，验证解析后的路径位于截图根目录内，只添加实际引用的文件。改写包内副本中的本地引用为 `assets/<安全文件名>`，保留远程 HTTP(S) 图片链接和其他 Markdown 内容。相同 basename 冲突时确定性重命名并同步更新引用。临时 ZIP 文件应使用唯一目录并在响应完成/失败后清理。

前端“下载笔记”改为调用此 API 保存 `.zip`；单独导出 Markdown 的入口若保留，必须与 ZIP 下载区分命名和操作，避免行为含糊。桌面/Web/浏览器扩展适用范围及接口复用策略在 ticket 中列明。

## 7. 视觉图像缓存与耗时观测

引入同一 task_id 自动重试可复用的视觉准备缓存：缓存拼接完成的网格图文件及元数据，不缓存膨胀的 base64 JSON。命中时跳过拼图并重新读取/编码网格；当前仍会重新抽帧，避免跨任务选帧共享与清理竞态。缓存键含视频指纹、采样输出/配置、网格与图像参数、schema；全局容量/数量 LRU 与 TTL 限制空间。原始帧数继续遵循用户配置；此改动不承诺端到端加速。

记录每阶段耗时和结果计数：抽帧、拼图、文件读取/base64 编码、视觉模型请求、笔记写盘；同时记录缓存命中/未命中、网格数量、输入总字节数和用户设置帧数。日志不得写入 API key、base64 图像内容或完整敏感本地路径。实际优化验收用相同视频与设置跑冷/热缓存对比，报告各阶段耗时和内容一致性。

## 8. 设置与 API 草案

- 配置项：`screenshot_retention_days` 默认 `7`；`media_retention_days` 默认 `3`；`0` 表示不自动清理。
- 设置变更只影响之后登记的资源；已有 `expires_at` 保持不变。
- 资源管理 API：列出资源统计/到期信息、查询清理预览、按类别清理、运行到期清理。
- 导出 API：按 `task_id` 返回 ZIP 流或临时文件响应，文件名安全处理。
- 所有破坏性清理端点限制为本机/已授权设置界面可调用，不提供任意文件路径输入。

## 9. 验收

- ZIP 含 `note.md` 与引用截图；解压后 Markdown 相对链接可定位图片；远程资源链接保持原样。
- 缺图、非法路径、重复文件名和特殊标题均有安全且明确行为；归档无目录穿越项。
- 新资源按创建时保留期固化过期时间；修改设置不影响旧资源；0 永不过期。
- 旧目录回填幂等，mtime + 默认期计算正确，过期资源可被回收；扫描不触碰未纳管目录。
- 自动清理只删除到期资源；手动按类别清理符合预览范围；失败可重试且不会删除笔记数据。
- 【已验证】视觉缓存冷/热路径图片顺序及内容一致（热路径复用网格、逐字节一致）、视频指纹/帧数/网格布局变化与条目损坏/过期均正确失效并重建、条目按 task_id 隔离。容量与过期清理有界。用例见 `tests/007-note-archive-and-media-cache/test_video_reader_cache.py`（9 个）。真实视频冷/热耗时基准、并发写入中断、磁盘满**仍未覆盖** —— 见 §13.3。
- 有阶段耗时和 cache hit/miss 观测；重复任务热缓存下可测得相应图像准备步骤耗时改善，未缓存路径回归无显著退化。
- 后端测试、前端测试、生产构建通过；spec tickets 与实现状态同步。

## 10. 实现清单

| # | 工单 | 状态 |
| --- | --- | --- |
| 01 | ZIP 笔记归档与资源路径改写 | 已完成（`tests/007-.../test_note_archive.py` 4 用例） |
| 02 | 媒体资源表、迁移与旧文件回填 | 已完成（`tests/007-.../test_media_resources.py` 4 用例） |
| 03 | 保留期配置、自动/手动清理与设置 UI | 已完成（`tests/007-.../test_media_resources.py` + `test_note_group_api.py` 32 用例） |
| 04 | 视觉准备缓存与阶段耗时观测 | 已完成（`tests/007-.../test_video_reader_cache.py` 9 用例；真实视频基准未做，见 §13.3） |
| 05 | 回归测试、基准与文档收尾 | 已完成（后端 579 passed；前端构建通过；真实视频基准未做） |

## 11. 待确认问题

无。范围与关键策略已由用户确认。

## 12. ⚠️ 2026-10-05 修订：缓存容量边界（来源：spec 009 需求④）

**修订来源**：用户要求「通用设置内加入一个缓存边界，本地的资源（已完成的任务的）到了设置的量就自动清理，不用等过期，防止长任务挤爆磁盘」。按 `specs/README.md:25` 的规则修订本 spec（本 spec 是「媒体缓存治理」的归属 spec，但 §3–§9 只覆盖**时间维度**，缺**容量维度**）。详细工单见 `specs/009-batch-grouping-and-long-run-robustness/tickets/07-cache-boundary.md`。

**被修订的既有决策**：§4 决策 5「设置语义：每类保留天数可配置；`0` 表示永不自动过期」——补充为「保留天数（时间维度）与总字节上限（容量维度）**并存**」；§8 配置项补充容量相关字段。

### 12.1 新增已定决策

| # | 决策 | 结论 |
| --- | --- | --- |
| 11 | 容量度量 | 三类资源（screenshot/video/audio）**合并**成一个总字节上限，不分类型单独设限 |
| 12 | 默认上限 | `cache_limit_bytes` 默认 **10 GiB**；`0` = 不限 |
| 13 | 清理策略 | **终态即清**：`SUCCESS` 与 `FAILED` 都算「已完成」；活跃/重试中的任务一律跳过；按最旧优先删到阈值以下 |
| 14 | 触发时机 | 每个任务到达终态时检查一次 + 复用现有 `media_cleanup_loop`（3600s）兜底；不引入 APScheduler/cron |
| 15 | 覆盖面 | 除 `media_resources` 登记的三类外，另纳入 `visual_cache`、`uploads/`、`data/note_output/`、系统 temp 的 ASR 切片（`asr_chunks_*` / `asr_speech_*`）、0 字节残骸文件 |
| 16 | visual_cache 归属 | **不**塞进 `media_resources` 表（`_managed_relative` 只接受文件、会拒绝目录）；沿用其既有 TTL/LRU 语义，但把 `backend/app/utils/video_reader.py:443-465` 的硬编码 2 GB/100 项改为读设置 |
| 17 | 磁盘门禁 | 新增 `shutil.disk_usage` 检查（此前全仓零命中）；剩余空间 < `min_free_disk_bytes`（默认 5 GiB）时拒绝新的生成提交；设置读失败时 fail-open 不拦截 |
| 18 | UI 落点 | 新增字段落在**通用设置**页（`BillNote_frontend/src/pages/SettingPage/general.tsx`），与既有「笔记生成并发」Card 并列；既有「媒体资源管理」页（`MediaRetention.tsx`）保持不变 —— 前者是容量维度，后者是时间维度 |

### 12.2 新增设置字段

`general_settings` 单行表新增（`create_all` 不给已有表加列，需在 `backend/app/db/init_db.py` 补幂等 `ALTER TABLE`）：

- `cache_limit_bytes`：默认 10 GiB，`0` = 不限；
- `min_free_disk_bytes`：默认 5 GiB；
- `circuit_breaker_threshold`：默认 5（连续失败熔断，见 spec 009 ticket 04）。

### 12.3 与既有验收的关系

§9 已有「自动清理只删除到期资源」等条目继续有效；本修订**不改变**时间维度语义 —— 容量清理是**额外**的触发条件，`cache_limit_bytes = 0` 时完全不介入。§3「非目标」中「不清理模型文件、数据库、笔记 Markdown/JSON」继续有效：容量清理只针对中间产物与已登记媒体，不动 `note_results/` 下的笔记正文与 `backend/models/` 的 whisper 模型。

### 12.4 实现清单追加

| # | 工单 | 状态 |
|---|---|---|
| 06 | 缓存容量边界（终态即清、最旧优先）与通用设置 UI | 已完成；详见 spec 009 ticket 07 |

## 13. 验证记录（2026-10-05，用户授权后执行）

### 13.1 门禁

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `cd backend; .venv\Scripts\python.exe -m pytest tests -q` | **579 passed**, 2 warnings, 13 subtests passed（exit 0） |
| spec 007 目录 | `cd backend; .venv\Scripts\python.exe -m pytest tests/007-note-archive-and-media-cache -q` | 61 passed |
| 前端构建 | `cd BillNote_frontend; pnpm build` | `✓ built in 1m 2s`，exit 0 |
| 凭据扫描 | 对全部 `git ls-files` 跟踪文件正则匹配 `sk-*` / `AKIA*` / `ghp_*` / `BEGIN PRIVATE KEY` / JWT / `Bearer <30+字符>` | **0 命中** |
| 前端类型 | `cd BillNote_frontend; pnpm exec tsc -p tsconfig.app.json --noEmit` | 110 errors（HEAD 基线 192，净减 82；110 条全部落在本 spec 未触碰或仅做删减的文件里） |

> **前端类型门禁的坑**：根 `tsconfig.json` 是 solution 式配置（`"files": []` + 只列
> `references`），不传 `-b`/`-p` 时 `tsc` 只解析这个空集合，**恒 exit 0、零输出**。
> 真正的门禁必须写 `tsc -p tsconfig.app.json --noEmit`。`package.json` 里没有任何
> typecheck 脚本，`pnpm build`（vite）也不做类型检查，所以这个假绿此前一直没暴露。

### 13.2 真实服务冒烟（端口 8483）

- `GET /api/sys_health` → `{"backend":"ok","ffmpeg":"ok","db":"ok"}`
- `GET /api/media/settings` → `{"screenshot_retention_days":7,"media_retention_days":3}`
- `GET /api/media/cleanup/preview` → `{"count":0,"bytes":0,"by_type":{...},"expires_earliest":null,"expires_latest":null}`
- `GET /api/media/cleanup/recent` → 审计行正常（`resource_types:["screenshot","video","audio"]`, `expired_only:true`）
- `GET /api/media/cache/limit` → 容量边界报告正常（`enabled:true`、`over_limit:false`、`by_kind.asr_temp`）

### 13.3 残余项（**未**通过验收，不得据本 spec 声称已完成）

1. **真实视频冷/热路径耗时基准**：无用真实长视频跑出的端到端数字。已证明的是「热路径
   跳过拼图」这一机制（用例用会抛异常的 `concat_images` 桩证明它没被调用），不是耗时改善幅度。
2. **并发写入、缓存写入中断、磁盘满**三类故障场景无自动化用例。并发语义由代码保证并在
   本轮加固，但未测。
3. **`schema` 版本变更导致 cache miss** 未单独用例（key 里含 `"schema": 1`）。
4. `_log_timing` 的分项耗时与「不记录图片内容/API key/本地绝对路径」由**代码检视**确认，
   无用例断言。

### 13.4 本轮修掉的真实缺陷（Windows）

`backend/app/utils/video_reader.py` 的视觉网格缓存写路径用 `os.rename(temporary_dir, cache_dir)`
落盘，`OSError` 时原本无条件丢弃自己刚建好的副本、保留旧目录。而 `os.rename` 在 Windows 上
**对已存在的目录直接失败**（POSIX 只在目录非空时失败），于是旧条目一旦损坏（`metadata.txt`
在、`grid_N.jpg` 缺失）：读路径正确判 miss → 重新拼图 → 写路径 rename 失败 → 丢掉新副本 →
旧损坏条目原样留下。结果是**每次重试都完整重做一遍拼图，且这个条目永远修不好**。

修法：抽出 `_cache_entry_valid(cache_dir)`（`metadata.txt` 存在 + 其声明的网格图都在且非空），
写路径 rename 失败时用它区分「并发写入者抢先放好的可用条目」（保留对方、只删自己的 tmp）与
「损坏/过期的旧条目」（先 `rmtree` 再 rename 原子替换）；读路径也改为复用同一判定，避免两处
逻辑再次漂移。该缺陷由
`test_corrupt_cache_entry_is_treated_as_miss_and_rebuilt` 首次运行时失败暴露。
