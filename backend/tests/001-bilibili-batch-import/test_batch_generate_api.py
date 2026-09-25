"""ticket 03：POST /api/generate_notes 的去重、入队与参数透传。"""
import json
from unittest import mock

from fastapi import BackgroundTasks

from app.routers import note as note_module
from app.routers.note import BatchGenerateRequest, generate_notes


def _body(resp):
    return json.loads(resp.body)


def _ready():
    return mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value={"ready": True},
    )


def _payload(items):
    return BatchGenerateRequest(
        platform="bilibili",
        items=items,
        quality="fast",
        model_name="m",
        provider_id="p",
    )


def test_skips_success_and_queues_rest():
    bg = BackgroundTasks()
    items = [
        {"bvid": "BV1done", "p": 1, "video_id": "BV1done",
         "url": "https://www.bilibili.com/video/BV1done"},
        {"bvid": "BV1new", "p": 2, "video_id": "BV1new_p2",
         "url": "https://www.bilibili.com/video/BV1new?p=2"},
    ]
    fake_gen = mock.Mock()
    with _ready(), \
         mock.patch.object(note_module, "_is_generated_task",
                           side_effect=lambda vid, plat: vid == "BV1done"), \
         mock.patch.object(note_module, "NoteGenerator", return_value=fake_gen):
        resp = generate_notes(_payload(items), bg)

    results = _body(resp)["data"]["results"]
    assert results[0] == {"video_id": "BV1done", "status": "skipped",
                          "reason": "already_generated"}
    assert results[1]["status"] == "queued"
    assert results[1]["video_id"] == "BV1new_p2"
    assert len(bg.tasks) == 1
    fake_gen._update_status.assert_called_once()

    task = bg.tasks[0]
    assert task.args[1] == "https://www.bilibili.com/video/BV1new?p=2"


def test_rejects_when_transcriber_not_ready():
    bg = BackgroundTasks()
    not_ready = {"ready": False, "reason": "model not ready",
                 "transcriber_type": "fast-whisper",
                 "model_size": "tiny", "downloading": False}
    with mock.patch(
        "app.services.transcriber_config_manager.TranscriberConfigManager.is_model_ready",
        return_value=not_ready,
    ):
        resp = generate_notes(_payload([{"bvid": "BV1a", "p": 1}]), bg)

    payload = _body(resp)
    assert payload["code"] == 300102
    assert payload["data"]["reason"] == "transcriber_model_not_ready"
    assert len(bg.tasks) == 0


def test_rejects_without_model_or_provider():
    bg = BackgroundTasks()
    req = BatchGenerateRequest(platform="bilibili", items=[], quality="fast",
                               model_name="", provider_id="")
    resp = generate_notes(req, bg)
    assert _body(resp)["code"] != 0
