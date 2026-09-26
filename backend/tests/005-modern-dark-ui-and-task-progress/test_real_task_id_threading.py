"""spec 005 ticket 14：真实 task_id 贯穿状态写入。

历史 bug：`_summarize_text()` 用 markdown 缓存文件名当 task_id
（`task_id = markdown_cache_file.stem`），于是 SUMMARIZING 状态被写进
`note_results/<task_id>_markdown.status.json`（幻影文件），真实状态文件一直停在
90%，前端看起来「卡在 90%」。`_transcribe_audio()` 也有同类反推。

这里固定：状态文件路径与 checkpoint key 都来自调用方传入的真实 task_id。
"""
import json

import pytest

from app.enmus.task_status_enums import TaskStage, TaskStatus
from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services import note as note_module
from app.services.note import NoteGenerator


def _record_status(record):
    def fake_update_status(
        task_id, status, message=None, *, stage=None, progress=None, stage_progress=None, detail=None
    ):
        record.append(
            {
                "task_id": task_id,
                "status": status,
                "stage": stage,
                "message": message,
                "stage_progress": stage_progress,
                "detail": detail,
            }
        )

    return fake_update_status


def _generator(record):
    generator = object.__new__(NoteGenerator)
    generator._update_status = _record_status(record)
    generator._handle_exception = lambda *args, **kwargs: None
    return generator


def _audio_meta():
    return AudioDownloadResult(
        file_path="a.mp3",
        title="标题",
        duration=1.0,
        cover_url=None,
        platform="bilibili",
        video_id="BV1",
        raw_info={"tags": ["测试"]},
        video_path=None,
    )


def _transcript():
    return TranscriptResult(
        language="zh",
        full_text="你好",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="你好")],
        raw={},
    )


def test_update_status_writes_the_real_task_file(tmp_path, monkeypatch):
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp_path)
    generator = object.__new__(NoteGenerator)

    generator._update_status(
        "real-task-id",
        TaskStatus.SUMMARIZING,
        stage=TaskStage.SUMMARIZING,
        message="正在调用模型生成笔记",
    )

    status_file = tmp_path / "real-task-id.status.json"
    assert status_file.exists(), "状态必须写进 <task_id>.status.json"
    data = json.loads(status_file.read_text(encoding="utf-8"))
    assert data["status"] == "SUMMARIZING"
    assert data["stage"] == "summarizing"
    assert data["message"] == "正在调用模型生成笔记"

    phantom = tmp_path / "real-task-id_markdown.status.json"
    assert not phantom.exists(), "不该再写 <task_id>_markdown.status.json 幻影文件"


def test_summarize_text_uses_real_task_id(tmp_path, monkeypatch):
    record = []
    generator = _generator(record)
    captured = {}

    class FakeSource:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeGpt:
        def summarize(self, source):
            return "# 标题\n\n正文"

    monkeypatch.setattr(note_module, "GPTSource", FakeSource)

    markdown_cache = tmp_path / "abc123_markdown.md"
    markdown = generator._summarize_text(
        _audio_meta(),
        _transcript(),
        FakeGpt(),
        markdown_cache,
        True,
        False,
        ["link"],
        None,
        None,
        [],
        task_id="real-task-id",
    )

    assert markdown.startswith("# 标题")
    assert markdown_cache.read_text(encoding="utf-8").startswith("# 标题")
    assert captured["checkpoint_key"] == "real-task-id", "checkpoint key 必须是真实 task_id"
    assert record[0]["task_id"] == "real-task-id"
    assert record[0]["status"] == TaskStatus.SUMMARIZING
    assert record[0]["stage"] == TaskStage.SUMMARIZING


def test_transcribe_audio_reports_with_real_task_id(tmp_path):
    record = []

    class FakeTranscriber:
        def transcript(self, file_path=None):
            return _transcript()

    generator = _generator(record)
    generator.transcriber = FakeTranscriber()

    result = generator._transcribe_audio(
        "a.mp3", tmp_path / "t_transcript.json", TaskStatus.TRANSCRIBING, task_id="real-task-id"
    )

    assert result is not None
    assert [entry["task_id"] for entry in record] == ["real-task-id"] * len(record)
    assert record[0]["status"] == TaskStatus.TRANSCRIBING
    assert (tmp_path / "t_transcript.json").exists()


def test_summarize_failure_records_real_task_id(tmp_path, monkeypatch):
    record = []
    generator = _generator(record)
    handled = []
    generator._handle_exception = lambda task_id, exc: handled.append(task_id)

    class BoomGpt:
        def summarize(self, source):
            raise RuntimeError("模型超时")

    with pytest.raises(RuntimeError):
        generator._summarize_text(
            _audio_meta(),
            _transcript(),
            BoomGpt(),
            tmp_path / "abc123_markdown.md",
            True,
            False,
            ["link"],
            None,
            None,
            [],
            task_id="real-task-id",
        )

    assert handled == ["real-task-id"]
