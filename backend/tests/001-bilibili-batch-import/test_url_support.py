"""ticket 01：B 站合集/系列 URL 的识别与规范化。"""
import pytest

from app.utils.url_parser import normalize_video_url, parse_bilibili_collection_url
from app.validators.video_url_validator import is_supported_video_url


COLLECTION_URLS = [
    "https://space.bilibili.com/14229967/lists/1533671?type=season",
    "https://space.bilibili.com/14229967/lists/1533671",
    "https://space.bilibili.com/1958703906/lists/547718?type=series",
    "https://space.bilibili.com/14229967/channel/collectiondetail?sid=1533671",
    "https://space.bilibili.com/14229967/channel/seriesdetail?sid=547718",
]


@pytest.mark.parametrize("url", COLLECTION_URLS)
def test_accepts_bilibili_collection_urls(url):
    assert is_supported_video_url(url) is True


def test_collection_url_not_normalized_to_video():
    url = "https://space.bilibili.com/14229967/lists/1533671?type=season"
    assert normalize_video_url(url) == url


@pytest.mark.parametrize("url,expected", [
    ("https://space.bilibili.com/1/lists/2?type=series",
     {"kind": "series", "mid": "1", "sid": "2"}),
    ("https://space.bilibili.com/1/lists/2",
     {"kind": "season", "mid": "1", "sid": "2"}),
    ("https://space.bilibili.com/1/channel/collectiondetail?sid=2",
     {"kind": "season", "mid": "1", "sid": "2"}),
    ("https://space.bilibili.com/1/channel/seriesdetail?sid=2",
     {"kind": "series", "mid": "1", "sid": "2"}),
])
def test_parse_collection_url(url, expected):
    assert parse_bilibili_collection_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://www.bilibili.com/video/BV147411K7xu",
    "https://www.bilibili.com/video/BV147411K7xu?p=2",
    "https://www.bilibili.com/anime/timeline",
    "",
])
def test_non_collection_url_returns_none(url):
    assert parse_bilibili_collection_url(url) is None


def test_video_url_still_supported():
    assert is_supported_video_url("https://www.bilibili.com/video/BV147411K7xu") is True
