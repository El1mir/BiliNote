"""spec 005 ticket 15：转写进度回调接线。

历史 bug：`_transcribe_audio()` 先调用 `self.transcriber.transcript(...)`，之后才
`setattr(transcriber, "progress_callback", ...)`，于是整段转写过程根本收不到回调，
前端在 TRANSCRIBING 阶段长时间无进度。

这里固定：调用 *之前* 安装回调、调用之后复原（转写器是单例，不能把回调留给下一个任务），
并且回调携带的是本次任务的真实 task_id。
"""
from app.enmus.task_status_enums import TaskStage, TaskStatus
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.note import NoteGenerator


def _generator(record, transcriber):
    generator = object.__new__(NoteGenerator)
    generator.transcriber = transcriber

    def fake_update_status(
        task_id, status, message=None, *, stage=None, progress=None, stage_progress=None, detail=None
    ):
        record.append(
            {
                "task_id": task_id,
                "status": status,
                "stage": stage,
                "message": message,
                "progress": progress,
                "stage_progress": stage_progress,
                "detail": detail,
            }
        )

    generator._update_status = fake_update_status
    generator._handle_exception = lambda *args, **kwargs: None
    return generator


def _transcript():
    return TranscriptResult(
        language="zh",
        full_text="你好",
        segments=[TranscriptSegment(start=0.0, end=1.0, text="你好")],
        raw={},
    )


class _FakeTranscriber:
    def __init__(self, on_call=None):
        self._on_call = on_call

    def transcript(self, file_path=None):
        if self._on_call:
            self._on_call(self)
        return _transcript()


def test_callback_is_installed_before_transcribe(tmp_path):
    record = []
    seen = {}

    def capture(transcriber):
        seen["has_callback"] = hasattr(transcriber, "progress_callback")
        callback = getattr(transcriber, "progress_callback", None)
        seen["callable"] = callable(callback)
        if callback:
            callback(3, 10)

    transcriber = _FakeTranscriber(on_call=capture)
    generator = _generator(record, transcriber)

    result = generator._transcribe_audio(
        "a.mp3", tmp_path / "t_transcript.json", TaskStatus.TRANSCRIBING, task_id="real-task-id"
    )

    assert result is not None
    assert seen["has_callback"] is True, "转写开始前就必须安装进度回调"
    assert seen["callable"] is True

    reports = [entry for entry in record if entry["stage_progress"] is not None]
    assert reports, "回调必须把进度写进状态文件"
    report = reports[0]
    assert report["task_id"] == "real-task-id"
    assert report["status"] == TaskStatus.TRANSCRIBING
    assert report["stage"] == TaskStage.TRANSCRIBING
    assert report["stage_progress"] == 30.0
    assert report["message"] == "正在转写 3/10"
    assert report["detail"] == {"current": 3, "total": 10, "unit": "segments"}


def test_callback_custom_message_is_forwarded(tmp_path):
    record = []

    def capture(transcriber):
        transcriber.progress_callback(4, 8, "已完成 4/8 段")

    generator = _generator(record, _FakeTranscriber(on_call=capture))

    generator._transcribe_audio(
        "a.mp3", tmp_path / "t_transcript.json", TaskStatus.TRANSCRIBING, task_id="real-task-id"
    )

    report = [entry for entry in record if entry["stage_progress"] is not None][0]
    assert report["message"] == "已完成 4/8 段"
    assert report["stage_progress"] == 50.0


def test_callback_is_removed_after_transcribe(tmp_path):
    transcriber = _FakeTranscriber()
    assert not hasattr(transcriber, "progress_callback")

    generator = _generator([], transcriber)
    generator._transcribe_audio(
        "a.mp3", tmp_path / "t_transcript.json", TaskStatus.TRANSCRIBING, task_id="real-task-id"
    )

    assert not hasattr(transcriber, "progress_callback"), "转写后必须摘掉回调，避免影响下一个任务"


def test_previous_callback_is_restored(tmp_path):
    sentinel = object()
    transcriber = _FakeTranscriber()
    transcriber.progress_callback = sentinel

    generator = _generator([], transcriber)
    generator._transcribe_audio(
        "a.mp3", tmp_path / "t_transcript.json", TaskStatus.TRANSCRIBING, task_id="real-task-id"
    )

    assert transcriber.progress_callback is sentinel


def test_each_task_gets_its_own_task_id(tmp_path):
    record = []
    seen_task_ids = []

    class RecordingTranscriber:
        def transcript(self, file_path=None):
            self.progress_callback(1, 1)
            return _transcript()

    transcriber = RecordingTranscriber()

    def fake_update_status(task_id, status, message=None, **kwargs):
        record.append(task_id)
        seen_task_ids.append(task_id)

    generator = object.__new__(NoteGenerator)
    generator.transcriber = transcriber
    generator._update_status = fake_update_status
    generator._handle_exception = lambda *args, **kwargs: None

    for index, task_id in enumerate(("task-a", "task-b")):
        generator._transcribe_audio(
            "a.mp3", tmp_path / f"t_{index}.json", TaskStatus.TRANSCRIBING, task_id=task_id
        )

    assert "task-a" in seen_task_ids and "task-b" in seen_task_ids
    assert "task-b" in seen_task_ids[-1:], "第二次调用必须换成 task-b 的回调"
    assert not hasattr(transcriber, "progress_callback")
