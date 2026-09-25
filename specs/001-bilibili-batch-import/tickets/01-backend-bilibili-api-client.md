# 01 · 后端：放宽 URL 校验 + B 站展开客户端

- **依赖**：无
- **关联**：spec §2-7 / §3 / §5.1

## 目标

让后端能识别 B 站合集/多P URL，并具备「展开」所需的数据获取能力。

## 改动点

1. `backend/app/validators/video_url_validator.py`
   - 新增合集 URL 识别：`space.bilibili.com/{mid}/lists/{sid}`（`?type=season|series`）、`channel/collectiondetail?sid=`。
   - 保留现有 `/video/BV...` 校验；合集 URL 不应被 `normalize_video_url` 丢弃。
2. 新增 `backend/app/bilibili/`（或就近 `downloaders/`）展开客户端：
   - `get_video_pages(bvid) -> list[Part]`：调 `/x/web-interface/view?bvid=`，取 `data.pages[]`（`page` / `part` / `duration` / `cid`）；单P 视频返回 `data.cid` 包装成 1 条。
   - `get_season_archives(mid, sid) -> list[VideoMeta]`：调 `/x/polymer/web-space/seasons_archives_list`，分页拉全，字段取 `bvid` / `title` / `duration` / `cover`。
   - `get_series_archives(mid, sid)`：`type=series` 时调 `/x/series/archives`。
   - cookie 复用 `CookieConfigManager().get("bilibili")`；请求头参考 `bilibili_subtitle.py`。

## 验收

- 单元测试：给定 mock JSON，`get_video_pages` 能返回分P 列表、单P 返回 1 条。
- 合集分页 > 30 条时能翻页拉全。
- 合集 URL 通过 `is_supported_video_url`，且不被规范化成单视频。
