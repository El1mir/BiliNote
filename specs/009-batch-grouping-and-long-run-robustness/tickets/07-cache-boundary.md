# 07 · 缓存边界（需求④，修订 007）与通用设置 UI

- **依赖**：无（但 `min_free_disk_bytes` 被 ticket 04 使用）
- **关联**：修订 `specs/007-note-archive-and-media-cache/spec.md` §12；本 spec §4 决策 16、§6
- **状态**：已完成

## 目标

通用设置内新增「缓存边界」：本地资源（已完成任务的）总量达到设定值就自动清理，不等过期，防止长任务挤爆磁盘。

## 背景

现有清理只认时间：`cleanup_resources(resource_types=None, expired_only=True, limit=200)`（`backend/app/services/media_resource_service.py:209-289`）只删 `expires_at <= now` 的记录，由 `media_cleanup_loop`（`:292-303`）每小时跑一次。spec 007 全程只有时间维度（截图 7 天 / 音视频 3 天），**没有任何容量上限设置项**。而 200 × 1–3 h 的 mp3 约 6–18 GB，开截图/视频理解则达数百 GB，3 天保留期内足以写满磁盘。

另外 `backend/app/utils/video_reader.py:443-465` 是全仓**唯一**按容量的边界，但硬编码（2 GB / 100 项 / 7 天）不可配置；`backend/uploads/`、`backend/data/note_output/`（`backend/app/utils/export.py:15 SAVE_PATH`）、系统 temp 的 ASR 切片（`backend/app/utils/audio_helper.py:28,46,67,171`）、0 字节残骸文件都不在任何清理器视野内。

## 改动点

1. **设置字段**（`backend/app/db/models/general_settings.py` 单行表，与 `media_settings` 同一套路）：
   - `cache_limit_bytes`：默认 **10 GiB**（`0` = 不限）；
   - `min_free_disk_bytes`：默认 **5 GiB**（供 ticket 04 的磁盘门禁使用）；
   - `circuit_breaker_threshold`：默认 **5**（供 ticket 04 的熔断使用）；
   - 同步 `backend/app/db/general_settings_dao.py`（`_get_or_create`、`get_general_settings`、`update_general_settings` + 归一化函数，参照 `normalize_max_parallel_notes` 的写法）与 `backend/app/routers/general.py`（`GeneralSettingsRequest` 增字段）；
   - `backend/app/db/init_db.py` 补幂等 `ALTER TABLE general_settings ADD COLUMN ...`（`create_all` 不给已有表加列，参照 `init_db.py:52-56`）。
2. **清理策略**（新增函数，放在 `backend/app/services/media_resource_service.py` 或同目录新 service）：
   - **终态即清**：`SUCCESS` 与 `FAILED` 都算「已完成」；活跃/重试中的任务（`_IN_FLIGHT_STATUSES`）一律跳过；
   - 计算「已登记三类资源 + visual_cache + uploads + note_output + ASR 临时切片 + 0 字节残骸」的**总字节**；
   - 超上限时按 **created_at / mtime 最旧优先**删除，直到降到阈值以下（留一定余量，避免每轮都刚好踩线）；
   - 上限为 `0` 时完全跳过容量清理（不影响既有时间维度清理）；
   - 写 `media_cleanup_runs` 审计行（沿用既有字段，注明触发原因）。
3. **覆盖面**：
   - `media_resources` 登记的三类（screenshot/video/audio）——沿用注册表，不绕过 `_managed_relative` 的路径防护；
   - `visual_cache`（`backend/data/visual_cache`）：**沿用既有 TTL/LRU 语义但阈值改为可配置**，**不**塞进 `media_resources` 表（`_managed_relative` 只接受文件、会拒绝目录）；`video_reader.py:443-465` 的硬编码 2 GB/100 项改为读设置；
   - `uploads/`、`data/note_output/`、系统 temp 的 ASR 切片目录（`asr_chunks_*` / `asr_speech_*`）、0 字节残骸文件。
4. **触发**：
   - 每个任务到达终态时检查一次；
   - 复用现有 `media_cleanup_loop`（`media_resource_service.py:292-303`，3600s）兜底；
   - **不**引入 APScheduler/cron（全仓目前零命中）。
5. **前端 UI**（落在用户指定的「通用设置」页 `BillNote_frontend/src/pages/SettingPage/general.tsx`，与现有「笔记生成并发」Card 并列）：
   - 缓存上限输入框（GB 展示、字节存储，`0` = 不限）+ 当前占用展示；
   - 磁盘剩余门禁阈值（GB）；
   - 熔断阈值（次）；
   - 同步 `BillNote_frontend/src/services/general.ts` 的类型与参数。
   - 现有 `pages/SettingPage/MediaRetention.tsx`（保留天数 + 手动清理）保持不变，两个入口职责不同：媒体资源管理 = 时间维度，通用设置 = 容量维度。

## 验收

- 总字节超上限时按最旧优先删到阈值以下；`0` 表示不限。
- 活跃/重试中的任务资源不被删除；SUCCESS 与 FAILED 都算「已完成」。
- visual_cache 超限时同样被回收，且阈值可配置（不再是硬编码 2 GB）。
- 修改上限只影响之后的清理，不需要重算已有记录的 `expires_at`。
- 通用设置页能读取与保存这些值；设置读失败时回落到默认值而不报 500。

## 测试

- `test_cache_limit_cleanup.py`：造最旧/最新资源与活跃任务资源，断言只删终态且最旧优先、删到阈值以下。
- `test_general_settings_cache_fields.py`：DAO 归一化、默认值、`0` 语义、读失败回落（**当前无任何 `test_general*.py`**，属新建覆盖）。
- 现有 `backend/tests/007-note-archive-and-media-cache/test_media_resources.py` 的路径防护用例（`'screenshot:../outside.jpg'` → failed==1 且文件仍在）必须继续通过。
