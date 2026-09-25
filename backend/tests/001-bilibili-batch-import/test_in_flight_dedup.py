"""spec 001 §12 / ticket 09：进行中的任务也要被去重跳过。"""
import json
from unittest import mock

import pytest

from app.routers import note as note_module


def _write_status(tmp_path, task_id, status, message=None):
    payload = {"status": status}
    if message:
        payload["message"] = message
    (tmp_path / f"{task_id}.status.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


@pytest.mark.parametrize("status,expected", [
    ("PENDING", True),
    ("PARSING", True),
    ("DOWNLOADING", True),
    ("TRANSCRIBING", True),
    ("SUMMARIZING", True),
    ("SAVING", True),
    ("SUCCESS", False),
    ("FAILED", False),
])
def test_in_flight_status_detection(tmp_path, status, expected):
    _write_status(tmp_path, "t1", status)
    with mock.patch.object(note_module, "NOTE_OUTPUT_DIR", str(tmp_path)), \
         mock.patch.object(note_module, "get_task_by_video", return_value="t1"):
        assert note_module._is_task_in_flight("BV1", "bilibili") is expected


def test_no_record_is_not_in_flight():
    with mock.patch.object(note_module, "get_task_by_video", return_value=None):
        assert note_module._is_task_in_flight("BV1", "bilibili") is False
        assert note_module._is_generated_task("BV1", "bilibili") is False


def test_only_success_counts_as_generated(tmp_path):
    _write_status(tmp_path, "t1", "SUCCESS")
    with mock.patch.object(note_module, "NOTE_OUTPUT_DIR", str(tmp_path)), \
         mock.patch.object(note_module, "get_task_by_video", return_value="t1"):
        assert note_module._is_generated_task("BV1", "bilibili") is True
        assert note_module._is_task_in_flight("BV1", "bilibili") is False


def test_missing_status_file_is_not_in_flight(tmp_path):
    with mock.patch.object(note_module, "NOTE_OUTPUT_DIR", str(tmp_path)), \
         mock.patch.object(note_module, "get_task_by_video", return_value="t1"):
        assert note_module._is_task_in_flight("BV1", "bilibili") is False
