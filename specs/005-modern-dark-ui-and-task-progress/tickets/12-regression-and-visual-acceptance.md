# 12 · 前端回归测试（遗留缺陷）

- **依赖**：03、04、05、06、08
- **关联**：spec §8
- **状态**：待实现（遗留缺陷）

> ⚠️ 2026-10-05 重新定义。原表述包含「暗色页面视觉验收」，随 m02324
> （浅色 DesignMD 是最终意图）失效。核查后本工单拆成两半：**后端已齐备，前端几乎空白**。

## 后端：已齐备

`backend/tests/005-modern-dark-ui-and-task-progress/` 下 7 个文件：

| 文件 | 钉住什么 |
| --- | --- |
| `test_task_stage_model.py` | `stage_for_status(TaskStatus.TRANSCRIBING) == TaskStage.TRANSCRIBING`；`stage_label(TaskStage.BUILDING_GRIDS) == "拼接网格图"`；`test_unknown_stage_progress_is_not_fabricated`（不伪造百分比） |
| `test_access_log_filter.py` | 200 → 过滤；500 与其他路径 → 放行 |
| `test_video_progress_callback.py` | 视频理解进度回调 |
| `test_transcriber_progress_wiring.py` | 转写进度接线（ticket 15 的回归） |
| `test_note_logger_fix.py` | note.py 统一 logger（ticket 13 的回归） |
| `test_real_task_id_threading.py` | 真实 task_id 贯穿（ticket 14 的回归） |
| `test_openai_asr_rate_limit.py` | ASR 限流 |

## 前端：几乎空白

只有 `BillNote_frontend/tests/005-modern-dark-ui/progress.test.ts`（22 行），**只测 `toPercent`**。

完全缺失的测试：

1. **任务适配**：`normalizeTaskStatus` 同时吃 snake_case 与 camelCase（`useTaskPolling.ts:12-21`）。
2. **未知阶段**：`ProgressTimeline.tsx:67` 的 `'queued'` 回退，以及 `index === -1` 时不能把阶段标成已完成
   （工单 08 缺陷 2/3 正是这条没被钉住才漏到现在）。
3. **无百分比阶段**：`progress` 为 `null` 时显示活动指示器而非伪造数值。
4. **时间线组件本身**：一个渲染测试都没有。

## 死代码清理

`BillNote_frontend/src/pages/HomePage/components/StepBar.tsx` 已无任何引用（`ProgressTimeline` 取代了它）。
它不依赖主题，所以没随工单 09 一起作废。

## 验收

- 上面 4 类前端测试补上并通过。
- `backend/.venv/Scripts/python.exe -m pytest`、`pnpm test`、`pnpm build` 全绿。
- `StepBar.tsx` 删除。
- 已有任务状态文件和持久化任务仍可继续打开。
