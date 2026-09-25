"""ticket 01：B 站展开客户端单元测试（全部 mock requests，不发真实请求）。"""
import unittest
from unittest import mock

from app.downloaders import bilibili_expand


def _resp(payload):
    resp = mock.Mock()
    resp.raise_for_status = mock.Mock()
    resp.json.return_value = payload
    return resp


def _view_multi_part():
    return {
        "code": 0,
        "data": {
            "bvid": "BV1xx411c7mD",
            "title": "多P视频",
            "cid": 111,
            "pages": [
                {"page": 1, "part": "P1 开头", "duration": 600, "cid": 111},
                {"page": 2, "part": "P2 结尾", "duration": "10:34", "cid": 222},
            ],
        },
    }


def _view_single_part():
    return {
        "code": 0,
        "data": {
            "bvid": "BV1yy411c7mD",
            "title": "单P视频",
            "cid": 999,
            "duration": 321,
            "pages": [],
        },
    }


class TestFetchVideoParts(unittest.TestCase):
    def test_multi_part_expands_all_pages(self):
        with mock.patch.object(
            bilibili_expand.requests, "get", return_value=_resp(_view_multi_part())
        ):
            parts = bilibili_expand.fetch_video_parts("BV1xx411c7mD")

        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0].p, 1)
        self.assertEqual(parts[0].title, "P1 开头")
        self.assertEqual(parts[0].duration, 600)
        self.assertEqual(parts[1].p, 2)
        self.assertEqual(parts[1].duration, 634)  # "10:34" -> 634s
        self.assertEqual(parts[1].cid, 222)

    def test_single_part_wrapped_as_one_entry(self):
        with mock.patch.object(
            bilibili_expand.requests, "get", return_value=_resp(_view_single_part())
        ):
            parts = bilibili_expand.fetch_video_parts("BV1yy411c7mD")

        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].p, 1)
        self.assertEqual(parts[0].duration, 321)
        self.assertEqual(parts[0].cid, 999)

    def test_api_error_returns_empty(self):
        payload = {"code": -404, "message": "啥都木有"}
        with mock.patch.object(
            bilibili_expand.requests, "get", return_value=_resp(payload)
        ):
            self.assertEqual(bilibili_expand.fetch_video_parts("BVdead"), [])

    def test_network_exception_returns_empty(self):
        with mock.patch.object(
            bilibili_expand.requests, "get", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(bilibili_expand.fetch_video_parts("BVdead"), [])


class TestParseDuration(unittest.TestCase):
    def test_int_and_str_forms(self):
        self.assertEqual(bilibili_expand._parse_duration(321), 321)
        self.assertEqual(bilibili_expand._parse_duration("10:34"), 634)
        self.assertEqual(bilibili_expand._parse_duration("1:02:03"), 3723)
        self.assertEqual(bilibili_expand._parse_duration(None), 0)
        self.assertEqual(bilibili_expand._parse_duration("bad"), 0)


class TestFetchCollection(unittest.TestCase):
    def _season_pages(self):
        page1 = {
            "code": 0,
            "data": {
                "meta": {"name": "合集标题", "cover": "cover.jpg", "mid": 14229967},
                "archives": [{"bvid": "BV1a", "title": "v1", "duration": 100, "cover": "a.jpg"}],
                "page": {"total": 2, "page_size": 1, "page_num": 1},
            },
        }
        page2 = {
            "code": 0,
            "data": {
                "archives": [{"bvid": "BV1b", "title": "v2", "duration": "3:20"}],
                "page": {"total": 2, "page_size": 1, "page_num": 2},
            },
        }
        return page1, page2

    def test_season_paginates_all_videos(self):
        page1, page2 = self._season_pages()

        def fake_get(url, params=None, **kwargs):
            self.assertEqual(url, bilibili_expand.API_SEASON_ARCHIVES)
            return _resp(page1 if params["page_num"] == 1 else page2)

        with mock.patch.object(bilibili_expand.requests, "get", side_effect=fake_get):
            info = bilibili_expand.fetch_collection("14229967", "1533671", "season")

        self.assertEqual(info.title, "合集标题")
        self.assertEqual(info.cover, "cover.jpg")
        self.assertEqual(info.owner_mid, "14229967")
        self.assertEqual([v.bvid for v in info.videos], ["BV1a", "BV1b"])
        self.assertEqual(info.videos[1].duration, 200)

    def test_series_uses_series_apis(self):
        meta = {"code": 0, "data": {"meta": {"name": "系列", "mid": 1958703906}}}
        archives = {
            "code": 0,
            "data": {
                "archives": [{"bvid": "BV1c", "title": "s1", "duration": 50}],
                "page": {"total": 1, "size": 30},
            },
        }
        seen = []

        def fake_get(url, params=None, **kwargs):
            seen.append(url)
            if url == bilibili_expand.API_SERIES_META:
                return _resp(meta)
            if url == bilibili_expand.API_SERIES_ARCHIVES:
                return _resp(archives)
            raise AssertionError(url)

        with mock.patch.object(bilibili_expand.requests, "get", side_effect=fake_get):
            info = bilibili_expand.fetch_collection("1958703906", "547718", "series")

        self.assertEqual(info.title, "系列")
        self.assertIn(bilibili_expand.API_SERIES_META, seen)
        self.assertIn(bilibili_expand.API_SERIES_ARCHIVES, seen)
        self.assertEqual([v.bvid for v in info.videos], ["BV1c"])

    def test_collection_skips_items_without_bvid(self):
        page = {
            "code": 0,
            "data": {
                "meta": {"name": "x"},
                "archives": [{"title": "no bvid"}, {"bvid": "BV1ok", "title": "ok"}],
                "page": {"total": 2, "page_size": 30},
            },
        }
        with mock.patch.object(bilibili_expand.requests, "get", return_value=_resp(page)):
            info = bilibili_expand.fetch_collection("1", "2", "season")
        self.assertEqual([v.bvid for v in info.videos], ["BV1ok"])


if __name__ == "__main__":
    unittest.main()
