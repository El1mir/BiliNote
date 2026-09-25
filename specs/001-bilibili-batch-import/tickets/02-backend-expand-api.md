# 02 · 后端：`POST /api/expand`

- **依赖**：01
- **关联**：spec §5.1

## 目标

提供两阶段流程的第一阶段：输入 URL，返回展开树（视频 + 分P + 去重标记）。

## 改动点

1. `backend/app/routers/note.py` 新增 `@router.post("/expand")`。
2. 入参 `ExpandRequest { url: str }`。
3. 判定 URL 类型：
   - 视频 → `bvid` → `get_video_pages`；
   - 合集 → `get_season_archives` / `get_series_archives`，再对每个 `bvid` 调 `get_video_pages`。
4. 每个 `video_id`（`BVxxx` / `BVxxx_pN`）查 `get_task_by_video`，填 `already_generated`。
5. 返回 spec §5.1 结构。

## 验收

- 合集 URL → 全部视频 + 分P；
- 多P视频 URL → 全部 P；
- 单P视频 URL → 单条；
- 非法 URL → 明确错误；
- 已生成条目 `already_generated=true`；
- 单条视频拉取失败不影响整批（见 spec 待确认 #1）。
