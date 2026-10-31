import pytest
from pydantic import ValidationError

from app.utils.url_parser import normalize_video_url
from app.validators.video_url_validator import VideoRequest


def test_watchlater_url():
    url = ("https://www.bilibili.com/list/watchlater/?bvid=BV1CPXpBYEui"
           "&oid=116294762371214&spm_id_from=333.881.0.0&vd_source=abc")
    assert normalize_video_url(url) == "https://www.bilibili.com/video/BV1CPXpBYEui"


def test_favlist_url():
    url = "https://www.bilibili.com/list/ml123456?bvid=BV1xx411c7mD&oid=987"
    assert normalize_video_url(url) == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_tracking_params_stripped():
    url = "https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333.881&vd_source=abc"
    assert normalize_video_url(url) == "https://www.bilibili.com/video/BV1xx411c7mD"


def test_p_number_preserved():
    url = "https://www.bilibili.com/video/BV1xx411c7mD?p=36&spm_id_from=333.881"
    assert normalize_video_url(url) == "https://www.bilibili.com/video/BV1xx411c7mD?p=36"


def test_no_bv_returned_unchanged():
    url = "https://www.bilibili.com/anime/timeline"
    assert normalize_video_url(url) == url


def test_b23_short_url_unchanged():
    url = "https://b23.tv/abc123"
    assert normalize_video_url(url) == url


def test_video_request_accepts_watchlater():
    req = VideoRequest(
        url="https://www.bilibili.com/list/watchlater/?bvid=BV1CPXpBYEui&oid=116294762371214",
        platform="bilibili",
    )
    assert str(req.url) == "https://www.bilibili.com/video/BV1CPXpBYEui"


def test_video_request_rejects_no_bv():
    with pytest.raises(ValueError):
        VideoRequest(url="https://www.bilibili.com/anime/timeline", platform="bilibili")


def test_note_router_request_accepts_watchlater():
    # note.py 里的 VideoRequest 才是 /generate_note 实际使用的请求模型
    from app.routers.note import VideoRequest as NoteVideoRequest

    req = NoteVideoRequest(
        video_url="https://www.bilibili.com/list/watchlater/?bvid=BV1CPXpBYEui&oid=116294762371214&spm_id_from=333.881.0.0",
        platform="bilibili",
        quality="fast",
        model_name="test-model",
        provider_id="test-provider",
    )
    assert req.video_url == "https://www.bilibili.com/video/BV1CPXpBYEui"


def test_video_request_rejects_platform_without_downloader():
    """youtube 的 downloader 已随死代码清理删除（spec 005 §12.5）。

    这个用例原先断言「youtube 链接照常通过、不被规范化」——前置条件是 youtube 还
    能生成笔记。现在入口校验与 SUPPORT_PLATFORM_MAP 一致，只放行 B 站，所以改成
    断言拒绝：放行的后果是用户排完队才撞 PLATFORM_NOT_SUPPORTED。
    """
    with pytest.raises(ValidationError):
        VideoRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", platform="youtube")
