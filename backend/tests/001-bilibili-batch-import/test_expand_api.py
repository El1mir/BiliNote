"""ticket 02：POST /api/expand 的展开、去重标记与单条错误隔离。"""
import json
from unittest import mock

from app.downloaders import bilibili_expand
from app.routers import note as note_module
from app.routers.note import ExpandRequest, expand


def _body(resp):
    return json.loads(resp.body)


def _part(p, title="", duration=0):
    return bilibili_expand.Part(p=p, title=title, duration=duration, cid=p)


def _collection_info(bvids):
    info = bilibili_expand.CollectionInfo(
        kind="season", mid="14229967", sid="1533671",
        title="合集标题", cover="cover.jpg", owner_mid="14229967",
    )
    info.videos = [
        bilibili_expand.VideoEntry(bvid=b, title=f"t-{b}", duration=100, cover=f"{b}.jpg")
        for b in bvids
    ]
    return info


def test_expand_collection_returns_videos_and_parts():
    info = _collection_info(["BV1a", "BV1b"])
    with mock.patch.object(note_module, "fetch_collection", return_value=info), \
         mock.patch.object(note_module, "fetch_video_parts",
                           side_effect=lambda bvid: [_part(1, "P1", 10), _part(2, "P2", 20)]), \
         mock.patch.object(note_module, "_is_generated_task", return_value=False):
        resp = expand(ExpandRequest(url="https://space.bilibili.com/14229967/lists/1533671?type=season"))

    data = _body(resp)["data"]
    assert data["type"] == "collection"
    assert data["title"] == "合集标题"
    assert data["owner"] == {"mid": "14229967", "name": ""}
    assert [v["bvid"] for v in data["videos"]] == ["BV1a", "BV1b"]
    assert [p["video_id"] for p in data["videos"][0]["parts"]] == ["BV1a_p1", "BV1a_p2"]
    assert data["videos"][0]["parts"][1]["url"].endswith("?p=2")
    assert data["videos"][0]["error"] is None


def test_expand_multi_part_video():
    with mock.patch.object(note_module, "fetch_video_parts",
                           return_value=[_part(1, "P1", 10), _part(2, "P2", 20)]), \
         mock.patch.object(note_module, "_is_generated_task", return_value=False):
        resp = expand(ExpandRequest(url="https://www.bilibili.com/video/BV147411K7xu?p=2"))

    data = _body(resp)["data"]
    assert data["type"] == "video"
    parts = data["videos"][0]["parts"]
    assert [p["p"] for p in parts] == [1, 2]
    assert parts[1]["video_id"] == "BV147411K7xu_p2"


def test_expand_single_part_video_uses_bvid_without_p():
    with mock.patch.object(note_module, "fetch_video_parts",
                           return_value=[_part(1, "唯一", 10)]), \
         mock.patch.object(note_module, "_is_generated_task", return_value=False):
        resp = expand(ExpandRequest(url="https://www.bilibili.com/video/BV147411K7xu"))

    part = _body(resp)["data"]["videos"][0]["parts"][0]
    assert part["video_id"] == "BV147411K7xu"
    assert part["url"] == "https://www.bilibili.com/video/BV147411K7xu"


def test_expand_marks_already_generated():
    with mock.patch.object(note_module, "fetch_video_parts",
                           return_value=[_part(1, "P1", 10), _part(2, "P2", 20)]), \
         mock.patch.object(note_module, "_is_generated_task",
                           side_effect=lambda vid, plat: vid == "BV147411K7xu_p2"):
        resp = expand(ExpandRequest(url="https://www.bilibili.com/video/BV147411K7xu"))

    parts = _body(resp)["data"]["videos"][0]["parts"]
    assert parts[0]["already_generated"] is False
    assert parts[1]["already_generated"] is True


def test_expand_part_failure_is_isolated():
    with mock.patch.object(note_module, "fetch_video_parts",
                           side_effect=RuntimeError("boom")):
        resp = expand(ExpandRequest(url="https://www.bilibili.com/video/BV147411K7xu"))

    entry = _body(resp)["data"]["videos"][0]
    assert entry["parts"] == []
    assert entry["error"]


def test_expand_invalid_url_returns_error():
    resp = expand(ExpandRequest(url="https://www.bilibili.com/anime/timeline"))
    payload = _body(resp)
    assert payload["code"] != 0
