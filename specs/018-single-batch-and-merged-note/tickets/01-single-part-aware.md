# 01 单集提交感知分P

- 依赖：无
- 关联 spec：§4 决策 8、§1 背景 1
- 目标：单集 `/generate_note` 对多P 链接使用与 `/expand` 一致的 `video_id`，不再把 P2 当 P1。

## 改动点

- `backend/app/routers/note.py` 的 `generate_note`：用 `extract_bilibili_p_number` 取 `p`，
  用 `fetch_video_parts(bvid)` 取分P 数（try/except，失败回退 `parts_count=0`），
  再 `build_video_id(bvid, p, parts_count)` 得到 `video_id`。
- `video_url` 保持用户提交的链接（含 `?p=N`），由 `normalize_video_url` 保证格式。
- 探测失败只 warning，不拒绝生成。

## 验收

- 多P 链接提交 `?p=3` 时任务行 `video_id == BV…_p3`；单P 链接仍是 `BV…`。
- `fetch_video_parts` 抛异常时任务照常入队，`video_id` 回退 `BV…`。
