"""spec 018 决策 9：合并任务的恢复载荷。

重启恢复只认 `_PAYLOAD_KEYS` 里的键；漏掉 merge_* 三项的话，重启后这条任务
会退化成「只生成第一条视频」的普通任务 —— 用户拿到的是一篇缺章节的笔记。
"""

import json

from app.services.task_recovery import _PAYLOAD_KEYS, _payload_from_row


def test_payload_keys_include_merge_fields():
    assert "merge_items" in _PAYLOAD_KEYS
    assert "merge_title" in _PAYLOAD_KEYS
    assert "merge_polish" in _PAYLOAD_KEYS


def test_payload_from_row_restores_merge_items():
    payload = {
        "video_url": "https://www.bilibili.com/video/BV1a?p=1",
        "platform": "bilibili",
        "merge_items": [
            {
                "url": "https://www.bilibili.com/video/BV1a?p=1",
                "video_id": "BV1a_p1",
                "title": "一",
            },
            {
                "url": "https://www.bilibili.com/video/BV1a?p=2",
                "video_id": "BV1a_p2",
                "title": "二",
            },
        ],
        "merge_title": "我的合集",
        "merge_polish": True,
        "group_id": None,
    }
    row = {
        "task_id": "task-9",
        "video_id": "merged_task-9",
        "platform": "bilibili",
        "payload_json": json.dumps(payload, ensure_ascii=False),
    }

    restored = _payload_from_row(row)

    assert restored is not None
    assert restored["task_id"] == "task-9"
    assert restored["merge_title"] == "我的合集"
    assert restored["merge_polish"] is True
    assert [item["video_id"] for item in restored["merge_items"]] == [
        "BV1a_p1",
        "BV1a_p2",
    ]
