# 04 · 视觉准备缓存与阶段耗时观测

- **依赖**：—
- **关联**：spec §4 决策 9；§7
- **状态**：已完成（后端验收已授权并执行，2026-10-05；残余项见文末）

## 目标

针对“开始编码图像”后静默约 6 分 40 秒的真实案例，分别量出图像准备和视觉模型请求耗时，并在安全、可验证的前提下复用重试任务已生成的视觉输入文件。

## 改动点

1. 基准化并分别记录抽帧、拼图、图片读取/base64、视觉请求、Markdown 写盘耗时；记录帧数、网格数、字节数和 cache hit/miss。
2. 为同一 task_id 的自动重试缓存拼接网格图及元数据；任务目录隔离并配合全局缓存叶节点 LRU/TTL，避免不同任务互删活动缓存。缓存 key 覆盖视频指纹、抽样结果/字幕与 LLM 时间点、用户帧数配置、grid 尺寸、图片处理参数和 cache schema 版本。
3. 缓存命中跳过拼图，按需从网格文件重新编码发送；不将巨大 base64 文本持久化。当前仍重做视频抽帧；避免跨任务共享选帧文件，因抽帧目录及平台源文件清理生命周期尚未形成可靠引用计数。本 ticket 不声称跳过抽帧或减少总任务耗时。
4. 使用有界大小/LRU 或期限清理缓存，原子写入；并发任务隔离，半成品或损坏缓存视为 miss 并安全重建。
5. 缓存失效时不得改变原处理结果；不缩小用户设置的帧数、不静默降质。
6. 对视觉模型请求记录开始、结束、模型标识和耗时；不记录图片内容、API key、敏感本地路径。

## 验收

- 【已验证】同视频同参数冷/热路径图片数量、顺序、内容一致；热路径复用网格。
  `tests/007-note-archive-and-media-cache/test_video_reader_cache.py::test_cold_path_writes_entry_and_hot_path_reuses_it`
  —— 热路径把 `concat_images` 换成会抛 `AssertionError("热路径不应重新拼图")` 的桩，
  证明它**确实跳过了拼图**；`hot_urls == cold_urls` 逐字节一致。
- 【已验证】改变视频指纹、帧数、网格布局后 cache miss。
  `test_cache_miss_when_video_content_changes` / `..._sampling_config_changes` / `..._grid_layout_changes`。
- 【已验证（损坏缓存）】损坏条目（metadata 声明 N 张、文件缺失）视为 miss 并**重建**。
  `test_corrupt_cache_entry_is_treated_as_miss_and_rebuilt`。该用例在首次运行时失败，
  并因此暴露了一个真实缺陷（见「实现说明」）。
- 【已验证（过期）】条目过期（TTL 7 天）不被复用，且被清理而不是永远占盘。
  `test_expired_cache_entry_is_not_reused_and_is_cleaned`。
- 【已验证（隔离）】缓存按 task_id 隔离，别的任务不能命中本任务的条目。
  `test_cache_entries_are_isolated_per_task`。
- 【仍待验证】热路径**图像准备时间改善**的真实视频基准（本机无真实长视频基准脚本；
  现有用例证明的是「跳过拼图」这一机制，不是端到端耗时数字）。
- 【仍待验证】并发写入、缓存写入中断、磁盘满三类故障场景。
  其中「并发」的语义已由代码保证并在本轮加固（见「实现说明」），但没有自动化用例。
- 【仍待验证】`schema` 版本变更导致 cache miss（key 里含 `"schema": 1`，未单独用例）。
- 【部分已验证】分项耗时完整、安全：`_log_timing` 记录 `phase`/`seconds`/`cache_hit`/`task_id`
  与 `frames`/`grids`/`image_count`/`input_bytes`/`data_url_bytes`，**不记录图片内容、
  API key 或本地绝对路径**（`fields` 只放计数与字节数）。由代码检视确认，无用例断言。
  视觉模型请求的耗时/模型标识属另一条链路（`backend/app/gpt/`），不在本 ticket 改动范围。
- 不宣称整体提速（抽帧仍重做）。

## 实现说明

- 当前复用范围仅为同一 task_id 的网格图缓存；视频抽帧仍会重新执行。
- **本轮修掉的真实缺陷（Windows）**：写路径用 `os.rename(temporary_dir, cache_dir)`
  落盘，失败时（`OSError`）原本无条件丢弃自己刚建好的副本、保留旧目录。而 `os.rename`
  在 Windows 上**对已存在的目录直接失败**（POSIX 只在目录非空时失败），于是当旧条目
  已损坏（metadata 在、`grid_N.jpg` 缺失）时：读路径正确判 miss → 重新拼图 → 写路径
  rename 失败 → 丢掉新副本 → 旧损坏条目原样留下。结果是**每次重试都完整重做一遍拼图，
  且这个条目永远修不好**。
  修法：抽出 `_cache_entry_valid(cache_dir)`（metadata 存在 + 声明的网格图都在且非空），
  写路径 rename 失败时用它区分「并发写入者抢先放好的可用条目」（保留对方、只删自己的
  tmp）与「损坏/过期的旧条目」（先 `rmtree` 再 rename 原子替换）；读路径也改为复用
  同一个判定，避免两处逻辑再次漂移。
- 真实冷/热基准、并发写入中断与磁盘满仍未覆盖；不宣称整体提速。
