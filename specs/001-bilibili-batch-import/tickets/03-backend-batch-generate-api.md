# 03 · 后端：`POST /api/generate_notes`

- **依赖**：01 / 02
- **关联**：spec §5.2 / §6

## 目标

批量接收勾选条目，去重后逐条入队，返回逐条状态。

## 改动点

1. `backend/app/routers/note.py` 新增 `@router.post("/generate_notes")`。
2. 入参 `BatchGenerateRequest { platform, items: [{bvid, p}], quality, model_name, provider_id, format, style, ... }`。
3. 每条构造 `video_id = f"{bvid}_p{p}"`（单P 可与 `bvid` 对齐，需与 yt-dlp info id 一致）。
4. 去重：`get_task_by_video(video_id, platform)` 命中 → `skipped`。
5. 复用现有 `run_note_task` + `task_serial_executor` 入队；构造带 `?p=N` 的规范 URL。
6. 返回 spec §5.2 结构。
7. 抽取现有 `/generate_note` 的公共逻辑，避免重复。

## 验收

- 去重命中返回 `skipped` 且不建 task；
- 参数透传正确；
- 混合成功/跳过/失败时逐个返回；
- 与单条 `/generate_note` 行为一致（同一视频产出相同 task 流程）。
