# 001 · B 站合集 / 多P 批量导入

- **状态**：implemented（2026-09-25 全部工单完成）
- **日期**：2026-09-25
- **范围**：B 站（bilibili.com）合集（season / series）与多P（anthology）视频
- **上游背景**：现有版本只支持一次提交单个 URL、生成单个笔记（`POST /api/generate_note`），且下载器显式 `noplaylist: True`，合集/多P 只能取到单集。

---

## 1. 目标

用户粘贴一个 **合集 URL** 或 **多P视频 URL** 后：

1. 后端展开出视频（及每个视频的分P）列表；
2. 前端在**较大的弹窗**里展示，用户可勾选（支持全选/全不选、`x-x` 范围选择）；
3. 提交后批量入队，逐条生成笔记；
4. 已生成过的条目自动跳过；失败条目自动重试 3 次，仍失败则该条标记失败、不阻塞其余。

### 非目标

- 不支持 YouTube playlist / 其他平台合集（保持现状），后续如要做另开 spec。
- 不改变现有「单视频即时生成」主流程的体验，批量是**增量入口**。
- 不引入新的任务队列中间件（Redis/Celery），复用现有 `ConcurrentTaskExecutor`。

---

## 2. 已定决策

| # | 决策 | 结论 |
|---|---|---|
| 1 | 视频 URL 语义 | 展开时**查询每个视频是否有分P**；有分P就展开成可勾选项（可全选），不再只取单集 |
| 2 | 流程形态 | **两阶段**：先展开 → 前端勾选 → 再批量提交 |
| 3 | 实现范围 | 后端 + 前端都改 |
| 4 | 去重键 | `(platform, video_id)`，其中多P 的 `video_id = BVxxx_pN` |
| 5 | 去重时机与范围 | **仅 `SUCCESS` 跳过**；失败 / 进行中允许重新提交（⚠️ 2026-09-26 修订为「进行中也跳过」，见 §12） |
| 6 | 失败处理 | 逐条失败不阻塞其余；返回逐条状态（`queued` / `skipped` / `failed`） |
| 7 | 失败重试 | 后端任务级自动重试，**首次 + 3 次重试（共 4 次尝试）**，指数退避 |
| 8 | 并发 | 复用现有执行器，`TASK_MAX_WORKERS` 默认 **5** |
| 9 | 数据来源 | 直接调 B 站 API（合集：`seasons_archives_list` / `series/archives`；分P：`/x/web-interface/view` 的 `pages[]`） |
| 10 | 端点 | 新增 `POST /api/expand` 与 `POST /api/generate_notes` |
| 11 | 前端载体 | Dialog 弹窗，大显示区 |
| 12 | 勾选默认 | **默认全选**；条目 > 200 时二次确认；不设硬上限 |
| 13 | `x-x` 范围 | **前端**解析成明确勾选列表，后端只收列表 |
| 14 | URL 带 `?p=N` | **预选该 P**，其余不选（尊重用户显式指定） |
| 15 | 展开单条失败 | 该条带 `error` 返回并置灰不可选，其余照常 |
| 16 | 任务列表展示 | 批量任务**按来源分组**（合集 / 视频），并加来源标签 |
| 17 | 重试状态文案 | 复用现有 status，message 标 `重试中 (n/3)` |
| 18 | 平台范围 | 仅 B 站 |
| 19 | 并发临时目录隔离 | `VideoReader` 每个实例使用唯一子目录、结束清理；ffmpeg 静音（见 §12） |

---

## 3. 关键事实（已核实）

- **现状**：`VideoRequest.video_url: str` 单链接；`is_supported_video_url` 只认 `bilibili.com/video/BV...`，**合集 URL 现在会被直接拒绝**（`PLATFORM_NOT_SUPPORTED`）。
- **下载器**：`bilibili_downloader.py` / `youtube_downloader.py` 均 `noplaylist: True`；单集下载需显式带 `?p=N`，无 `p` 时 yt-dlp 取第 1 集。
- **多P id**：yt-dlp 对 anthology 的 info id 为 `BVxxx_pN`，故 DB 中 `video_task.video_id` 天然区分每一集。
- **去重 DAO**：`get_task_by_video(video_id, platform)` 现成可用；`/generate_note` 里的去重调用目前被注释掉。需注意该 DAO 只返回 `task_id`，判断「是否 SUCCESS」需再读 task 状态。
- **执行器**：`task_serial_executor.py` 是 `ThreadPoolExecutor`，默认 3，可由 `TASK_MAX_WORKERS` 覆盖。
- **转写**：当前 `.env` 为本地 `fast-whisper / tiny`，批量并发对 CPU/内存敏感。
- **模型基类**：`Downloader.download()` 抽象方法签名含 `skip_download`，各实现未完全对齐，批量路径不依赖它。

---

## 4. 流程

```text
用户粘贴 URL
   │
   ▼
POST /api/expand ──► 判定 URL 类型
   │                   ├─ 视频：查 pages[] → 分P 列表
   │                   └─ 合集：分页拉 archives → 每个视频再查 pages[]
   │
   ▼
返回展开树（含 already_generated 标记、单条 error）
   │
   ▼
前端 Dialog 展示 / 勾选（全选、x-x、全不选；默认全选；>200 二次确认）
   │
   ▼
POST /api/generate_notes（勾选后的 [{bvid, p}] 列表）
   │
   ├─ 去重：仅 SUCCESS 记录 → skipped
   ├─ 逐条建 task（复用现有 NoteGenerator / run_note_task）
   ├─ 失败任务后端自动重试（首次 + 3 次）
   └─ 返回 [{video_id, p, task_id, status}]
   │
   ▼
前端 taskStore 批量加入（按来源分组），逐条轮询状态
```

---

## 5. 接口设计

### 5.1 `POST /api/expand`

请求：

```json
{ "url": "https://space.bilibili.com/14229967/lists/1533671?type=season" }
```

响应：

```json
{
  "platform": "bilibili",
  "type": "collection",
  "title": "合集标题",
  "cover": "https://...",
  "owner": { "mid": 14229967, "name": "UP名" },
  "videos": [
    {
      "bvid": "BV147411K7xu",
      "title": "视频标题",
      "duration": 1234,
      "cover": "https://...",
      "already_generated": false,
      "error": null,
      "parts": [
        { "p": 1, "title": "P1 标题", "duration": 600, "already_generated": false },
        { "p": 2, "title": "P2 标题", "duration": 634, "already_generated": true }
      ]
    }
  ]
}
```

- `type` 取值 `video` / `collection`。
- **单P 视频 `parts` 为长度 1 的数组**（统一结构，前端无需特判）。
- 展开中单条失败：该条带 `error` 字符串、`parts` 为空，前端置灰不可选，其余照常返回。

### 5.2 `POST /api/generate_notes`

请求：

```json
{
  "platform": "bilibili",
  "items": [{ "bvid": "BV147411K7xu", "p": 2 }],
  "quality": "fast",
  "model_name": "...",
  "provider_id": "...",
  "format": [],
  "style": "minimal",
  "screenshot": false,
  "link": false,
  "video_understanding": false
}
```

响应：

```json
{
  "results": [
    { "video_id": "BV147411K7xu_p2", "task_id": "uuid", "status": "queued" },
    { "video_id": "BV1xx411c7XX_p1", "status": "skipped", "reason": "already_generated" },
    { "video_id": "BV1yy411c7YY_p1", "status": "failed", "reason": "..." }
  ]
}
```

- 复用的生成参数（quality/model/provider/style/...）由前端一次性传入，套用到批内所有条目。
- `video_id` 约定为 `BVxxx_pN`（单P 也是 `_p1`），与 yt-dlp info id / DB 记录保持一致。

---

## 6. 去重

- 键：`(platform, video_id)`，`video_id` 为 `BVxxx_pN`。
- 时间点：**入队前**检查。
- 规则：**仅当已有记录为 `SUCCESS` 时跳过**（返回 `skipped`）；`FAILED` / 进行中的记录允许重新提交。
  - ⚠️ **2026-09-26 修订**：实测「进行中允许重复提交」会导致同一视频并发互踩，已改为「进行中也跳过」，详见本文 §12。
- 实现：`get_task_by_video` 拿到 `task_id` 后，再读该 task 的 `.status.json` 判断是否 `SUCCESS`。

---

## 7. 重试

- 层级：**后端任务级**（覆盖下载 / 转写 / LLM 全流程），不是仅网络层。
- 次数：**首次 + 3 次重试 = 共 4 次尝试**。
- 退避：指数退避 5s / 15s / 45s（可配置）。
- 状态：重试期间复用现有 status，message 标 `重试中 (n/3)`（n 为已重试次数）。
- 达上限后写 `FAILED`，批量端点据此返回 `failed`。
- 前端已有 `retryTask` 手动重试保留，作为兜底。

---

## 8. 前端交互

- 入口：现有 `NoteForm` 的链接输入框旁新增「批量导入」按钮；识别到合集 URL 时也可自动提示。
- 弹窗：Dialog，显示区足够大；表格列 = 勾选 / 标题 / 时长 / 分P / 状态（已生成置灰）。
- 选择：
  - **默认全选**（可生成的条目）；
  - 全选 / 全不选按钮；
  - `x-x` 范围输入框，**前端解析**成勾选集；
  - URL 带 `?p=N` 时**预选该 P**，其余不选；
  - 条目 > 200 时提交弹二次确认。
- 提交：调用 `/api/generate_notes`，把返回的 `task_id[]` 批量加入 `taskStore`。
- 任务列表：批量任务**按来源分组**（合集名 / 单视频），并加来源标签。
- 轮询：复用 `useTaskPolling`。

---

## 9. 测试要点

- `expand`：
  - 合集 URL → 全部视频 + 分P；
  - 多P 视频 URL → 展开全部 P；
  - 单P 视频 URL → `parts` 长度 1；
  - 非法 / 不支持 URL → 明确错误；
  - 合集分页边界（>30 条）；
  - 单条失败时带 `error` 且不阻塞整批。
- `generate_notes`：
  - 去重仅跳过 `SUCCESS`；`FAILED` 可重提；
  - 混合成功/跳过/失败；
  - 参数透传正确。
- 重试：构造「前 N 次失败后成功」的桩，断言重试次数与最终状态；「首次 + 3 次」语义。
- 前端：全选 / 全不选 / `x-x` 解析（含 `3-3`、越界、倒序）单测。

---

## 10. 决策记录（原待确认问题 → 已解决）

| # | 问题 | 决议 | 理由 |
|---|---|---|---|
| 1 | 展开单条失败如何处理 | 该条带 `error`、置灰不可选，其余照常 | 一个坏条目不应废掉整个合集 |
| 2 | URL 带 `?p=N` 是否预选 | 预选该 P，其余不选 | 尊重用户显式指定 |
| 3 | `x-x` 解析在前端还是后端 | 前端解析成勾选集 | 后端只收明确列表，接口更稳定 |
| 4 | 「重试 3 次」语义 | 首次 + 3 次重试（共 4 次尝试） | 与「重试 3 次」字面一致 |
| 5 | 去重是否跳过进行中/失败 | 仅 `SUCCESS` 跳过 | 失败/进行中应允许重试 |
| 6 | 批量任务列表展示 | 按来源分组 + 来源标签 | 几百条任务需要可读性 |
| 7 | 合集规模上限 | 不硬限，> 200 二次确认 | 防手滑而非防功能 |
| 8 | 重试期间状态文案 | `重试中 (n/3)` | 复用现有 status 机制 |

---

## 11. 实现清单

> 仅记录工单标题与状态，施工细节见 `tickets/`。

| # | 工单 | 状态 |
|---|---|---|
| 01 | 后端：放宽 URL 校验 + B 站展开客户端 | ✅ 已完成 |
| 02 | 后端：`POST /api/expand` | ✅ 已完成 |
| 03 | 后端：`POST /api/generate_notes` | ✅ 已完成 |
| 04 | 后端：任务级自动重试 | ✅ 已完成 |
| 05 | 配置：批量并发默认值 `TASK_MAX_WORKERS=5` | ✅ 已完成 |
| 06 | 前端：展开弹窗与勾选 | ✅ 已完成 |
| 07 | 前端：批量提交与任务列表 | ✅ 已完成 |
| 08 | 并发隔离：`VideoReader` 实例级唯一目录 + 清理 + ffmpeg 静音 | ✅ 已完成 |
| 09 | 并发隔离：去重纳入「进行中」状态 | ✅ 已完成 |
| 10 | 日志降噪：截图 ffmpeg 与调试 print | ✅ 已完成 |

---

## 12. 并发任务临时目录隔离（2026-09-26 追加）

### 现象

`TASK_MAX_WORKERS=5` 引入并发后，生成任务出现大量错误并最终 `FAILED`：

- `WinError 32: 另一个程序正在使用此文件` —— 同一视频被多个任务同时下载到 `data/data/BVxxx.mp4`；
- `FileNotFoundError: .../output_frames/frame_00_08.jpg` → `ValueError: 视频处理失败` —— 并发任务互相清空对方的抽帧结果；
- 大量 `[libdav1d] Unknown Metadata OBU type 6`（ffmpeg 噪音，非致命但刷屏）。

### 根因

| 共享资源 | 位置 | 冲突 |
|---|---|---|
| 抽帧目录 | `VideoReader` 默认 `get_app_dir("output_frames")` | `run()` 清空整个目录、`group_images()` 列出整个目录 → 并发任务互相删除/混合帧 |
| 缩略图目录 | 默认 `get_app_dir("grid_output")` | `grid_{idx}.jpg` 文件名冲突 |
| 同一视频重复任务 | 去重仅跳过 `SUCCESS`（§6） | 进行中可重复提交 → 同一视频并发跑多份 |

### 决策

| # | 决策 | 结论 |
|---|---|---|
| 1 | 抽帧/缩略图目录 | `VideoReader` 每个实例使用**唯一子目录**（`output_frames/<token>`、`grid_output/<token>`），运行结束清理 |
| 2 | ffmpeg 噪音 | `ffprobe` / 抽帧统一 `loglevel quiet`，错误靠 `check=True` 捕获；截图 ffmpeg 加 `-loglevel error`，调试 `print` 改 `logger.debug`（2026-09-26 扩展到截图/下载路径） |
| 3 | 去重范围修正 | **进行中（PENDING/PARSING/...）也跳过**，不再允许重复提交同一视频 |
| 4 | 下载文件隔离 | 同一视频由「进行中跳过」保证不并发；不同视频 id 不同，天然不冲突（本轮不改 5 个 downloader 的签名） |
| 5 | 重试防并发 | 重试（带 `task_id`）也要检查该 task_id 是否在跑，避免单任务被并发跑两遍（2026-09-26 追加，ticket 11） |
| 6 | 状态轮询误判 | 前端单次轮询失败不再判任务失败（连续 5 次才判），全局 axios 超时 10s → 30s（ticket 11） |

### 验收

- 两个不同视频并发跑 `video_understanding` 时互不影响，均成功；
- 同一视频在任务进行中重复提交，批量返回 `skipped (reason=in_progress)`，单条返回「该视频正在生成中」；
- 抽帧日志不再出现 `libdav1d` 刷屏；
- 任务结束后 `data/output_frames/<token>` 与 `data/grid_output/<token>` 被清理。

### 工单

| # | 工单 | 状态 |
|---|---|---|
| 08 | `VideoReader` 实例级唯一目录 + 清理 + ffmpeg 静音 | ✅ 已完成 |
| 09 | 去重纳入「进行中」状态 | ✅ 已完成 |
| 10 | 日志降噪：截图 ffmpeg 与调试 print | ✅ 已完成 |
