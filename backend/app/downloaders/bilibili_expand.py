"""B 站合集 / 分P 展开客户端。

只负责「取数据」，不下载、不入队、不写库：
  - 视频分P：GET /x/web-interface/view?bvid=  → data.pages[]
  - 合集 season：GET /x/polymer/web-space/seasons_archives_list（分页）
  - 系列 series：GET /x/series/archives + /x/series/series（分页）

cookie 复用 CookieConfigManager（AI 字幕/风控接口需要登录态时可选注入）。

设计见 specs/001-bilibili-batch-import/spec.md §5.1。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import requests

from app.services.cookie_manager import CookieConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_SEASON_ARCHIVES = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
API_SERIES_ARCHIVES = "https://api.bilibili.com/x/series/archives"
API_SERIES_META = "https://api.bilibili.com/x/series/series"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PAGE_SIZE = 30
TIMEOUT = 10


@dataclass
class Part:
    """一个分P。"""

    p: int
    title: str
    duration: int = 0
    cid: Optional[int] = None

    def to_dict(self) -> dict:
        return {"p": self.p, "title": self.title, "duration": self.duration}


@dataclass
class VideoEntry:
    """合集里的一个视频（parts 由调用方按需补齐）。"""

    bvid: str
    title: str = ""
    duration: int = 0
    cover: str = ""
    parts: list = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "bvid": self.bvid,
            "title": self.title,
            "duration": self.duration,
            "cover": self.cover,
            "parts": [p.to_dict() for p in self.parts],
            "error": self.error,
        }


@dataclass
class CollectionInfo:
    kind: str  # "season" | "series"
    mid: str
    sid: str
    title: str = ""
    cover: str = ""
    owner_mid: str = ""
    owner_name: str = ""
    videos: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "mid": self.mid,
            "sid": self.sid,
            "title": self.title,
            "cover": self.cover,
            "owner": {"mid": self.owner_mid, "name": self.owner_name},
            "videos": [v.to_dict() for v in self.videos],
        }


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #

def _headers() -> dict:
    h = {"User-Agent": UA, "Referer": "https://www.bilibili.com"}
    cookie = CookieConfigManager().get("bilibili")
    if cookie:
        h["Cookie"] = cookie
    return h


def _get_data(url: str, params: dict) -> Optional[dict]:
    """GET 一个 B 站接口，返回 data 字段；任何异常/业务错误返回 None。"""
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001 - 展开失败不应让整批挂掉
        logger.warning("B站接口请求失败 %s: %s", url, e)
        return None

    if payload.get("code") != 0:
        logger.warning(
            "B站接口返回错误 %s: code=%s msg=%s",
            url, payload.get("code"), payload.get("message"),
        )
        return None
    return payload.get("data") or {}


def _parse_duration(value) -> int:
    """B 站时长可能是 int 秒或 "MM:SS" 字符串，统一成秒。"""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            seconds = 0
            for chunk in value.split(":"):
                seconds = seconds * 60 + int(chunk)
            return seconds
        except (ValueError, TypeError):
            return 0
    return 0


# --------------------------------------------------------------------------- #
# 分P
# --------------------------------------------------------------------------- #

def fetch_video_parts(bvid: str) -> list:
    """取一个视频的全部分P；单P视频返回长度 1 的列表（spec §5.1）。"""
    data = _get_data(API_VIEW, {"bvid": bvid})
    if not data:
        return []

    pages = data.get("pages") or []
    if pages:
        parts = []
        for page in pages:
            parts.append(Part(
                p=int(page.get("page") or len(parts) + 1),
                title=page.get("part") or "",
                duration=_parse_duration(page.get("duration")),
                cid=page.get("cid"),
            ))
        return parts

    # 单P视频：没有 pages，用顶层 cid 包装成 1 条
    cid = data.get("cid")
    if cid:
        return [Part(
            p=1,
            title=data.get("title") or "",
            duration=_parse_duration(data.get("duration")),
            cid=cid,
        )]
    return []


# --------------------------------------------------------------------------- #
# 合集 / 系列
# --------------------------------------------------------------------------- #

def _fetch_season_archives(mid: str, sid: str) -> tuple:
    first = _get_data(API_SEASON_ARCHIVES, {
        "mid": mid, "season_id": sid, "page_num": 1, "page_size": PAGE_SIZE,
    })
    if not first:
        return {}, []

    meta = first.get("meta") or {}
    archives = list(first.get("archives") or [])
    page = first.get("page") or {}
    total = int(page.get("total") or len(archives))
    page_size = int(page.get("page_size") or PAGE_SIZE) or PAGE_SIZE

    page_num = 1
    while len(archives) < total:
        page_num += 1
        data = _get_data(API_SEASON_ARCHIVES, {
            "mid": mid, "season_id": sid, "page_num": page_num, "page_size": page_size,
        })
        batch = (data or {}).get("archives") or []
        if not batch:
            break
        archives.extend(batch)

    return meta, archives


def _fetch_series_archives(mid: str, sid: str) -> tuple:
    meta_data = _get_data(API_SERIES_META, {"series_id": sid}) or {}
    meta = meta_data.get("meta") or {}

    first = _get_data(API_SERIES_ARCHIVES, {
        "mid": mid, "series_id": sid, "pn": 1, "ps": PAGE_SIZE,
    })
    if not first:
        return meta, []

    archives = list(first.get("archives") or [])
    page = first.get("page") or {}
    total = int(page.get("total") or len(archives))
    page_size = int(page.get("size") or PAGE_SIZE) or PAGE_SIZE

    pn = 1
    while len(archives) < total:
        pn += 1
        data = _get_data(API_SERIES_ARCHIVES, {
            "mid": mid, "series_id": sid, "pn": pn, "ps": page_size,
        })
        batch = (data or {}).get("archives") or []
        if not batch:
            break
        archives.extend(batch)

    return meta, archives


def fetch_collection(mid: str, sid: str, kind: str = "season") -> CollectionInfo:
    """拉取合集/系列的全部视频（不含分P，分P由调用方按需 fetch_video_parts）。"""
    if kind == "series":
        meta, archives = _fetch_series_archives(str(mid), str(sid))
    else:
        meta, archives = _fetch_season_archives(str(mid), str(sid))

    info = CollectionInfo(
        kind=kind,
        mid=str(mid),
        sid=str(sid),
        title=meta.get("name") or "",
        cover=meta.get("cover") or "",
        owner_mid=str(meta.get("mid") or ""),
    )

    for item in archives:
        bvid = item.get("bvid")
        if not bvid:
            continue
        info.videos.append(VideoEntry(
            bvid=bvid,
            title=item.get("title") or "",
            duration=_parse_duration(item.get("duration")),
            cover=item.get("cover") or "",
        ))

    logger.info(
        "展开合集 kind=%s mid=%s sid=%s: %d 个视频", kind, mid, sid, len(info.videos),
    )
    return info


# --------------------------------------------------------------------------- #
# id / url 规范化（与 yt-dlp 的 info id 对齐）
# --------------------------------------------------------------------------- #

def build_video_id(bvid: str, p: int, parts_count: int) -> str:
    """计算任务的规范 video_id。

    yt-dlp 对多P（anthology）的 info id 是 ``BVxxx_pN``，单P 视频则是 ``BVxxx``；
    去重键必须与此一致，否则单P 会永远匹配不上。
    """
    if parts_count and parts_count > 1:
        return f"{bvid}_p{int(p)}"
    return bvid


def build_video_url(bvid: str, p: int, parts_count: int) -> str:
    """构造用于生成任务的链接。

    多P 带 ``?p=N``；单P **不能**带 p，否则 yt-dlp 会把单P 当成 ``_p1``。
    """
    base = f"https://www.bilibili.com/video/{bvid}"
    if parts_count and parts_count > 1:
        return f"{base}?p={int(p)}"
    return base
