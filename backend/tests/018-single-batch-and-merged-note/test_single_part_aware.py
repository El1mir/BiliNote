"""spec 018 决策 8：单集提交的 video_id 要带分P后缀。

不修的话有两个真实缺陷：`already_generated` 永远匹配不上；同一视频不同分P
会被在途判定互相挡住。
"""

from unittest import mock

from app.routers import note as note_module
from app.routers.note import _resolve_single_video_id


def _parts(count):
    return [
        mock.Mock(p=index + 1, title=f"P{index + 1}", duration=10)
        for index in range(count)
    ]


def test_multi_part_uses_part_suffix(monkeypatch):
    monkeypatch.setattr(note_module, "fetch_video_parts", lambda bvid: _parts(3))
    video_id = _resolve_single_video_id(
        "BV1RPC1BbEVN", "https://www.bilibili.com/video/BV1RPC1BbEVN?p=3", "bilibili"
    )
    assert video_id == "BV1RPC1BbEVN_p3"


def test_multi_part_without_p_defaults_to_first(monkeypatch):
    """没有 ?p= 时按 P1 处理，但 id 仍带后缀 —— 与 /expand 的 build_video_id 一致。"""
    monkeypatch.setattr(note_module, "fetch_video_parts", lambda bvid: _parts(4))
    video_id = _resolve_single_video_id(
        "BV1RPC1BbEVN", "https://www.bilibili.com/video/BV1RPC1BbEVN", "bilibili"
    )
    assert video_id == "BV1RPC1BbEVN_p1"


def test_single_part_has_no_suffix(monkeypatch):
    monkeypatch.setattr(note_module, "fetch_video_parts", lambda bvid: _parts(1))
    video_id = _resolve_single_video_id(
        "BV1abc", "https://www.bilibili.com/video/BV1abc?p=1", "bilibili"
    )
    assert video_id == "BV1abc"


def test_probe_failure_falls_back_to_bare_id(monkeypatch):
    def boom(bvid):
        raise RuntimeError("网络抖动")

    monkeypatch.setattr(note_module, "fetch_video_parts", boom)
    video_id = _resolve_single_video_id(
        "BV1abc", "https://www.bilibili.com/video/BV1abc?p=2", "bilibili"
    )
    assert video_id == "BV1abc"


def test_empty_parts_falls_back_to_bare_id(monkeypatch):
    monkeypatch.setattr(note_module, "fetch_video_parts", lambda bvid: [])
    video_id = _resolve_single_video_id(
        "BV1abc", "https://www.bilibili.com/video/BV1abc", "bilibili"
    )
    assert video_id == "BV1abc"


def test_other_platforms_are_untouched(monkeypatch):
    def boom(bvid):  # pragma: no cover - 不该被调用
        raise AssertionError("非 bilibili 不该探测分P")

    monkeypatch.setattr(note_module, "fetch_video_parts", boom)
    assert (
        _resolve_single_video_id("yt-abc", "https://youtu.be/yt-abc", "youtube")
        == "yt-abc"
    )
