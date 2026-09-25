"""spec 001 §12 / ticket 09：批量端点对进行中的视频返回 skipped。"""
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
        platform="bilibili", items=items, quality="fast",
        model_name="m", provider_id="p",
    )


def test_batch_skips_in_progress_task():
    bg = BackgroundTasks()
    items = [{"bvid": "BV1running", "p": 1, "video_id": "BV1running",
              "url": "https://www.bilibili.com/video/BV1running"}]
    fake_gen = mock.Mock()
    with _ready(), \
         mock.patch.object(note_module, "_is_generated_task", return_value=False), \
         mock.patch.object(note_module, "_is_task_in_flight", return_value=True), \
         mock.patch.object(note_module, "NoteGenerator", return_value=fake_gen):
        resp = generate_notes(_payload(items), bg)

    results = _body(resp)["data"]["results"]
    assert results[0]["status"] == "skipped"
    assert results[0]["reason"] == "in_progress"
    assert len(bg.tasks) == 0
