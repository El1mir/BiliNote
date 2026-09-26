# 08 · 高价值采样：限制方式二选一（每秒上限 / 全片上限）

- **依赖**：01、02、04、05
- **关联**：spec §1A、§4，⚠️ 修订 01/02/04/05
- **状态**：✅ 已完成
- **日期**：2026-09-26

## 背景

原高价值采样只用一个 `max_frames`（全片上限），且算法内**每秒只保留 1 帧**。
实际使用中发现需要能表达两种不同的采样预算，且**二选一**：

1. **每秒上限**：画面变化剧烈的片段希望每秒多留几帧 → 「每秒最多采样 x 帧」；
2. **全片上限**：希望整个视频最多交给模型 y 帧 → 「全片最多采样 y 帧」。

两者**只生效一个**，不是叠加。

## 已定语义（二选一）

新增 `frame_limit_mode`：

| 模式 | 生效参数 | 行为 | 默认 |
|---|---|---|---|
| `total`（默认） | `max_frames` | 收全部候选 → 按时间**均匀降采样**到该上限 | 60（下限 5，**不设上限**——几小时的课程需要更大预算，2026-09-26 调整） |
| `per_second` | `frames_per_second` | 每秒最多保留 N 个候选，**不做全片总量截断** | 2（范围 1–10） |

- **批量模式**：`max_frames` 是**每个视频各自的上限**（per_second 同理按每个视频各自计算），
  不会因为视频多而被摊薄。
- 另一个未选中的参数**完全不生效**（后端也会忽略）。

## 改动点

### 后端
1. `frame_sampler._dedupe_by_second(timestamps, max_per_second=None)`：
   `None`/`<=0` 表示不设每秒上限；仍做毫秒级精确去重；
2. `select_smart_timestamps(..., frame_limit_mode="total")`：
   - `per_second`：按秒分桶取前 N，直接返回；
   - `total`：收取全部候选，再 `_downsample_evenly(max_frames)`（保留首尾）；
   - 两种模式都**保留亚秒精度**（不再 `int()` 截断）；
3. `VideoReader` 新增 `frame_limit_mode`；
   - 文件名仍整秒用 `frame_MM_SS.jpg`，同秒多帧追加毫秒 `frame_MM_SS_mmm.jpg`；
   - `extract_time_from_filename` / `concat_images` 标签兼容两种格式；
   - `per_second` 模式不设总量上限，抽帧时不再受 `extract_frames` 默认 1000 截断；
4. `NoteGenerator.generate` / `_download_media` / `run_note_task` /
   `VideoRequest` / `BatchGenerateRequest` 全链路透传 `frames_per_second` + `frame_limit_mode`。

### 前端
5. `NoteForm` schema / defaultValues / reset / `batchDefaults` 新增
   `frames_per_second`（默认 2）与 `frame_limit_mode`（默认 `total`）；
6. 高价值采样时显示「**限制方式**」下拉（全片最大帧数 / 每秒最大帧数），
   并按所选模式**只显示对应的一个输入框**；
7. `services/note.ts` 的 `generateNote` 与 `BatchGeneratePayload` 补两个字段。

## 测试

- `backend/tests/002-video-understanding-sampling/test_frame_sampler.py`：
  两种模式各自只生效一个、`per_second` 每秒分桶、`total` 均匀降采样、亚秒精度；
- `.../test_video_reader_sampling.py`：`frames_per_second` / `frame_limit_mode` 透传、亚秒文件名生成/解析。

## 验收

- 选择「每秒最大帧数」时只按每秒上限抽帧，`max_frames` 不生效；
- 选择「全片最大帧数」时只按全片上限均匀降采样，每秒上限不生效；
- 同一秒多帧能正确抽取、命名、排序、拼图；
- 批量生成时每个视频各自计算。
