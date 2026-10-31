from app.services.source_intake import resolve_bilibili_inputs  # type: ignore[reportMissingImports]


def test_resolve_bilibili_video_and_part():
    result = resolve_bilibili_inputs(
        [
            "https://www.bilibili.com/video/BV1abc123456?p=2",
        ]
    )
    item = result["items"][0]
    assert item["source"] == "bilibili"
    assert item["kind"] == "part"
    assert item["sourceId"] == "BV1abc123456"
    assert item["part"] == 2
    assert item["state"] == "ready"


def test_resolve_rejects_unsupported_source_without_adapter_call():
    result = resolve_bilibili_inputs(["https://www.youtube.com/watch?v=abc"])
    item = result["items"][0]
    assert item["state"] == "unsupported"
    assert item["error"]["code"] == "unsupported_source"


def test_resolve_deduplicates_same_canonical_item():
    result = resolve_bilibili_inputs(
        [
            "https://www.bilibili.com/video/BV1abc123456?share_source=copy",
            "https://www.bilibili.com/video/BV1abc123456",
        ]
    )
    assert result["summary"]["readyCount"] == 1
    assert result["summary"]["duplicateCount"] == 1
    assert result["items"][1]["duplicateOf"] == result["items"][0]["itemId"]


def test_resolve_marks_items_after_input_limit():
    result = resolve_bilibili_inputs(
        ["https://www.bilibili.com/video/BV1abc123456"] * 3,
        limits={"maxInputUrls": 2},
    )
    assert result["items"][2]["state"] == "limit_exceeded"
    assert result["items"][2]["error"]["code"] == "collection_limit_exceeded"
