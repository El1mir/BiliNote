"""ticket 03：POST /api/generate_notes 的去重、入队与参数透传。

spec 009 起批量入口不再用 ``BackgroundTasks``（Starlette 那是 ``for`` 循环 await，
严格串行），改为把每条任务丢进分发池，所以这里 patch ``_dispatch_note_task`` 观察入队。
"""

import json
from unittest import mock

from fastapi import BackgroundTasks

from app.db.note_group_dao import NoteGroupError
from app.enmus.note_enums import DownloadQuality
from app.routers import note as note_module
from app.routers.note import BatchGenerateRequest, generate_notes


def _body(resp):
    return json.loads(resp.body)


def _ready():
    return mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value={"ready": True},
    )


def _payload(items, group_name=None):
    return BatchGenerateRequest(
        platform="bilibili",
        items=items,
        quality=DownloadQuality.fast,
        model_name="m",
        provider_id="p",
        group_name=group_name,
    )


def _run(
    items,
    group_name=None,
    generated=None,
    in_flight=None,
    create_group=None,
    disk_error=None,
):
    """跑一次 generate_notes，返回 (响应体, 分发的 kwargs 列表, _enqueue_task mock)。"""
    bg = BackgroundTasks()
    dispatched = []
    fake_gen = mock.Mock()
    group_patch = (
        mock.patch("app.db.note_group_dao.create_group", **create_group)
        if create_group
        else mock.patch(
            "app.db.note_group_dao.create_group",
            return_value={"id": "gid-1", "name": group_name or ""},
        )
    )
    with (
        _ready(),
        mock.patch.object(
            note_module, "_is_generated_task", return_value=bool(generated)
        ),
        mock.patch.object(
            note_module, "_is_task_in_flight", return_value=bool(in_flight)
        ),
        mock.patch.object(note_module, "_check_disk_space", return_value=disk_error),
        mock.patch.object(note_module, "_enqueue_task") as enqueue,
        mock.patch.object(
            note_module,
            "_dispatch_note_task",
            side_effect=lambda kw: dispatched.append(kw),
        ),
        mock.patch.object(note_module, "NoteGenerator", return_value=fake_gen),
        group_patch,
    ):
        resp = generate_notes(_payload(items, group_name), bg)
    return _body(resp), dispatched, enqueue, bg


def test_skips_success_and_queues_rest():
    bg = BackgroundTasks()
    items = [
        {
            "bvid": "BV1done",
            "p": 1,
            "video_id": "BV1done",
            "url": "https://www.bilibili.com/video/BV1done",
        },
        {
            "bvid": "BV1new",
            "p": 2,
            "video_id": "BV1new_p2",
            "url": "https://www.bilibili.com/video/BV1new?p=2",
        },
    ]
    dispatched = []
    fake_gen = mock.Mock()
    with (
        _ready(),
        mock.patch.object(
            note_module,
            "_is_generated_task",
            side_effect=lambda vid, plat: vid == "BV1done",
        ),
        mock.patch.object(note_module, "_is_task_in_flight", return_value=False),
        mock.patch.object(note_module, "_enqueue_task"),
        mock.patch.object(
            note_module,
            "_dispatch_note_task",
            side_effect=lambda kw: dispatched.append(kw),
        ),
        mock.patch.object(note_module, "NoteGenerator", return_value=fake_gen),
    ):
        resp = generate_notes(_payload(items), bg)

    results = _body(resp)["data"]["results"]
    assert results[0] == {
        "video_id": "BV1done",
        "status": "skipped",
        "reason": "already_generated",
    }
    assert results[1]["status"] == "queued"
    assert results[1]["video_id"] == "BV1new_p2"
    assert len(dispatched) == 1
    assert dispatched[0]["video_url"] == "https://www.bilibili.com/video/BV1new?p=2"
    # 批量入口不再走 BackgroundTasks（那会退化成串行）
    assert len(bg.tasks) == 0
    fake_gen._update_status.assert_called_once()


def test_rejects_when_transcriber_not_ready():
    bg = BackgroundTasks()
    not_ready = {
        "ready": False,
        "reason": "model not ready",
        "transcriber_type": "fast-whisper",
        "model_size": "tiny",
        "downloading": False,
    }
    with mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value=not_ready,
    ):
        resp = generate_notes(_payload([{"bvid": "BV1a", "p": 1}]), bg)

    payload = _body(resp)
    assert payload["code"] == 300102
    assert payload["data"]["reason"] == "transcriber_model_not_ready"
    assert len(bg.tasks) == 0


def test_empty_batch_does_not_require_an_active_model():
    bg = BackgroundTasks()
    req = BatchGenerateRequest(
        platform="bilibili",
        items=[],
        quality=DownloadQuality.fast,
    )
    with mock.patch.object(note_module, "resolve_active_model", side_effect=RuntimeError("no active model")):
        resp = generate_notes(req, bg)
    assert _body(resp)["code"] == 0
    assert _body(resp)["data"]["results"] == []


# --------------------------------------------------------------------------
# spec 009 ticket 01：批量分组
# --------------------------------------------------------------------------


def test_batch_creates_one_group_for_the_whole_batch():
    """一批 3 条 → 只建 1 个组，3 条都带同一个 group_id。"""
    items = [
        {"bvid": "BV1a", "p": 1, "video_id": "BV1a"},
        {"bvid": "BV1b", "p": 1, "video_id": "BV1b"},
        {"bvid": "BV1c", "p": 1, "video_id": "BV1c"},
    ]
    body, dispatched, enqueue, _bg = _run(items, "我的合集")
    assert body["code"] == 0
    assert body["data"]["group_id"] == "gid-1"
    assert len(dispatched) == 3
    for kw in dispatched:
        assert kw["group_id"] == "gid-1"
    assert enqueue.call_count == 3
    for call in enqueue.call_args_list:
        assert call.args[3] == "gid-1"


def test_batch_without_group_name_stays_ungrouped():
    body, dispatched, enqueue, _bg = _run(
        [{"bvid": "BV1a", "p": 1, "video_id": "BV1a"}], None
    )
    assert body["data"]["group_id"] is None
    assert dispatched[0]["group_id"] is None
    assert enqueue.call_args.args[3] is None


def test_no_group_created_when_everything_is_skipped():
    """整批都被跳过时不该留下一个空组（spec 009 决策 5）。"""
    items = [
        {"bvid": "BV1a", "p": 1, "video_id": "BV1a"},
        {"bvid": "BV1b", "p": 1, "video_id": "BV1b"},
    ]
    created = []
    body, dispatched, _enqueue, _bg = _run(
        items,
        "我的合集",
        generated=True,
        create_group={
            "side_effect": lambda name: created.append(name) or {"id": "gid-x"}
        },
    )
    assert body["code"] == 0
    assert body["data"]["group_id"] is None
    assert created == []  # 没建组
    assert dispatched == []


def test_group_create_failure_reports_explicit_error():
    """建组失败必须明确报错，不能静默退化成未分组（spec 009 决策 4）。"""
    body, dispatched, _enqueue, _bg = _run(
        [{"bvid": "BV1a", "p": 1, "video_id": "BV1a"}],
        "我的合集",
        create_group={"side_effect": NoteGroupError("分组数量已达上限（1000）")},
    )
    assert body["code"] == 300105
    assert body["data"]["reason"] == "group_create_failed"
    assert dispatched == []


def test_payload_json_is_recorded_for_restart_recovery():
    """入队时要把完整生成参数落库，否则重启后无法还原（ticket 03）。"""
    _body_, _dispatched, enqueue, _bg = _run(
        [{"bvid": "BV1a", "p": 1, "video_id": "BV1a"}]
    )
    payload = enqueue.call_args.args[4]
    assert isinstance(payload, dict)
    assert payload["video_url"] == "https://www.bilibili.com/video/BV1a"
    assert "model_name" not in payload
    assert "provider_id" not in payload
    assert "task_id" not in payload


def test_disk_gate_rejects_batch():
    """剩余空间不足时整批拒绝（spec 009 决策 11）。"""
    body, dispatched, _enqueue, _bg = _run(
        [{"bvid": "BV1a", "p": 1}], disk_error="磁盘剩余空间不足：当前剩余 1.0 GB"
    )
    assert body["code"] == 300104
    assert body["data"]["reason"] == "insufficient_disk_space"
    assert dispatched == []
