# 018 单集/批量分离与合并笔记

> 状态：implemented（2026-10-18）
> 来源：用户需求（本轮 goal）——「<https://www.bilibili.com/video/BV1RPC1BbEVN> 有分P，但直接点生成没有检测分P」
> 关联：spec 001（批量导入）、spec 009（批量建组）、spec 017（Web 重构后批量面板仍在，但入口与分P感知退化）

## 1. 背景

重构后的工作区只有一个「粘贴链接 → 生成笔记」表单，批量导入是页头一个独立按钮打开的面板。实际使用暴露两个问题：

1. **单集入口不分P**：`POST /generate_note` 用 `extract_video_id` 只取 `BV…`，不带 `_pN`。于是多P 视频（如 BV1RPC1BbEVN）直接点生成时：
   - yt-dlp 在 `noplaylist=True` 下只取第一集，用户以为生成了「整部视频」；
   - 任务行的 `video_id` 是裸 `BV…`，与 `/expand` 里 `build_video_id` 算出的 `BV…_pN` 不一致 → 「已生成」标记永远匹配不上，且同一视频不同 P 之间会被 `_is_task_in_flight` 互相挡住。
2. **批量入口不显眼、也没有范围选择**：用户要么在页头找按钮，要么整批勾选；几十 P 的合集只能一个个点。

同时用户希望批量多一个**合并任务**模式：把多个视频的笔记合成**一个**任务笔记（不建组），而默认（不合并）仍然是「一次批量 = 一个组 + 多条任务笔记」。

## 2. 目标

- 工作区输入区明确分成 **单集生成** 与 **批量生成** 两个模式（Tab 切换）。
- 单集模式粘贴到多P 链接时**自动切到批量**并展开分P 列表（用户决策 2026-10-18）。
- 批量模式：先查询分集/合集标题 → 勾选 / 列表序号范围选择 / 全选 → 建组提交。
- 批量新增「合并任务」开关：
  - 不勾选（默认）：整批新建一个组，每个视频一条任务笔记（= 现状）。
  - 勾选：**不建组**，只产生**一条**任务，把所选视频的笔记合并成一篇。
- 合并时可选「让模型润色」（用户决策：结构拼接与模型改写两种都要，默认结构拼接）。

## 3. 非目标

- 不改任务队列/并发/限流语义（spec 009/012 不变）。
- 不为合并笔记提供「再拆分」或跨平台合并。
- 不改浏览器扩展与 Tauri 桌面端。
- 不做「已有笔记直接复用进合并」（合并一律重新生成，语义可预测）。

## 4. 已定决策

1. **模式分离**：输入区用 Tab 切换 `单集生成` / `批量生成`；页头原来的「批量导入」按钮移除，避免两套入口。
2. **单集多P → 自动切批量**（用户决策 2026-10-18）：单集模式在 URL 稳定后（去抖 600ms）探测 `/expand`；若该视频 `parts > 1`，切到批量 Tab 并把该链接预填、自动展开，用户直接在分P 列表里勾。单P 链接不打扰。
3. **合并笔记 = 一条任务**（用户决策）：`merge=true` 时后端只生成一个 `task_id`、写一行任务记录（`video_id = merged_<task_id 前 8 位>`）、`group_id = NULL`；不调用 `_resolve_batch_group`。
4. **合并成品默认结构拼接**：顶部 `# {合并标题}` + 目录 + 每个视频一个 `## {i}. {标题}`，正文原样保留（标题层级整体降 1 级，代码围栏内的 `#` 不动），截图链接继续指向 `/static/screenshots/` 因此仍然可用。不额外调用模型。
5. **可选模型润色**（用户决策「两者都要」）：`merge_polish=true` 时把结构拼接结果整体交给当前模型改写一次；若请求体超过 `max_request_bytes` 预算则跳过润色、保留结构拼接结果并在日志里留痕（不做静默截断）。
6. **部分失败保留成果**（用户决策）：逐个视频生成，成功的照样合并；失败的列在笔记末尾「未生成成功的视频」一节，任务仍判 SUCCESS，但状态消息写明失败条数。全部失败才判 FAILED。
7. **页码范围只按列表序号**（用户决策）：一个全局输入（如 `3-6,9`）作用于展开后的扁平列表序号（合集按顺序、单个多P 视频的序号即 P 号），复用 `parseRangeSelection`。
8. **单集 `video_id` 修正**：`/generate_note` 提交时用 `fetch_video_parts` 探测分P 数，再用 `build_video_id(bvid, p, parts_count)` 得到与 `/expand` 一致的 `BV…_pN`；探测失败（网络/需要 Cookie）回退成裸 `BV…`，不阻断生成。
9. **合并任务的恢复与重试**：`payload_json` 里带 `merge_items` / `merge_title` / `merge_polish`；`task_recovery._PAYLOAD_KEYS` 一并放行，重启后仍能按原参数重跑。

## 5. 接口草案

### 5.1 `POST /api/generate_notes`（扩展）

```jsonc
{
  "platform": "bilibili",
  "items": [{ "bvid": "BV1xx", "p": 3, "video_id": "BV1xx_p3", "url": "https://www.bilibili.com/video/BV1xx?p=3" }],
  "quality": "medium",
  "group_name": "某合集",          // merge=false 时必填；merge=true 时忽略
  "merge": false,                  // 新增
  "merge_title": "某合集",         // 新增；merge=true 时作为合并笔记标题
  "merge_polish": false            // 新增；merge=true 且为 true 时调用模型润色
}
```

响应（merge=true）：`{ "results": [{ "video_id": "BV1xx_p3", "task_id": "<唯一>", "status": "queued" }], "group_id": null }`

### 5.2 合并执行

`run_note_task(..., merge_items=[{url,title,video_id,p}], merge_title=..., merge_polish=...)`：
逐条用 `NoteGenerator.generate()` 在**内部 task_id**（`<task_id>-s{i}`，不落库）上跑完整流水线，收集 markdown/转写/时长，最后合并写回外层 `task_id`。

## 6. 流程

1. 单集：粘贴 → 探测 →（单P）直接生成；（多P）自动切批量。
2. 批量：粘贴一个/多个链接 → 解析 → 列表（含标题、时长、已生成标记）→ 勾选/范围/全选 → 填组名或勾「合并任务」并填合并标题 → 提交。
3. 合并：后端建一条任务 → 逐条生成 → 合并 → 保存 → SUCCESS（消息含 `N/M 个视频`）。

## 7. 测试要点

- `note_merge`：标题降级不动代码围栏、目录锚点、失败清单、空列表、单条。
- `/generate_notes`：merge=true 不建组、只入队一条、items 为空报错、在途分P 拒绝。
- `run_note_task` 合并分支：部分失败仍 SUCCESS、全部失败 FAILED、进度消息含序号。
- 恢复：`payload_json` 含 `merge_items` 时能还原。
- 前端：`parseRangeSelection`（沿用 001 用例）、合并开关时组名字段隐藏、多P 自动切批量。

## 8. 实现清单（2026-10-18）

| 工单 | 状态 | 说明 |
| --- | --- | --- |
| 01 单集分P 感知 | resolved | `_resolve_single_video_id` + `extract_bilibili_p_number`；探测失败回退裸 `BV…`；单集任务行 video_id 与 `/expand` 一致 |
| 02 合并服务与接口 | resolved | `app/services/note_merge.py`、`MERGE_NOTES_PROMPT`、`UniversalGPT.polish_markdown`、`/generate_notes` 新增 `merge` / `merge_title` / `merge_polish` |
| 03 合并执行与恢复 | resolved | `_run_merged_note_task` + `NoteGenerator.generate(persist_metadata=False)`；`_PAYLOAD_KEYS` / `PAYLOAD_KEYS` / `_build_task_kwargs` 同步三个键（spec 015 契约测试通过） |
| 04 前端模式与批量面板 | resolved | `IntakePanel`（Tab 常驻切换）、单集多P 自动切批量、列表序号范围选择、合并开关 + 合并标题 + 润色开关 |
| 05 测试与验证 | resolved | 见下方验证证据 |

### 验证证据（2026-10-18）

- 后端：`.venv\Scripts\python.exe -m pytest tests/018-single-batch-and-merged-note -q` → **25 passed**；全量 `-m pytest -q` → **917 passed**（修复前另有 2 条 spec 015 契约失败：`_build_task_kwargs` 缺三个 merge 键，已补）。
- 前端：`pnpm vitest run` → **34 passed**（含恢复的 001 `parseRangeSelection`、004 `normalizeMathDelimiters`、005 `toPercent`、010 `isTaskInFlight` 用例 —— 重构时这三个 util 被删、测试一直红着）；`pnpm exec tsc -b` exit 0；`pnpm build` ✓；`pnpm lint` exit 0。
- 浏览器（Playwright headless，1440×1000，Vite dev 3015 + 后端 8483）：
  - 工作区出现「单集生成 / 批量生成」两个 tab，默认单集，单集有 `#video-url` 与「生成笔记」；
  - 单集粘贴 `https://www.bilibili.com/video/BV1RPC1BbEVN` → **自动切到批量并展开「已展开 1 个视频，共 52 个分P」**（用户报的问题：直接点生成只跑 P1，已修复）；
  - 批量：`#batch-range` 输入 `1-2` 点「应用范围」→「已选中 2 项」；
  - 打开「合并为一个任务」→ 组名字段消失、`#batch-merge-title` 出现、润色开关出现、提交按钮变「合并生成 2 个视频」；
  - console error 0、失败请求 0。

- ⚠️ 运行中的后端进程（8483）是改动前启动的：合并接口要重启后端才生效（`run.bat` 或 `python main.py`）；前端 dev 已通过 HMR 生效。
