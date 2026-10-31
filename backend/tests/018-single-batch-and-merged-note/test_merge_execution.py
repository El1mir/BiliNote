"""spec 018：合并任务执行（逐条生成 → 合并 → 存成一条任务）。

这里把 NoteGenerator / 保存 / 容量清理都换成假的，只保留
`_run_merged_note_task` 自己的编排逻辑 —— 真正要钉住的是：

* 子生成用内部 task_id 且 `persist_metadata=False`（不能多出任务行）；
* 部分失败仍判 SUCCESS，失败项写进笔记末尾；
* 全部失败才判 FAILED；
* 润色开关只在 merge_polish=True 时调用模型。
"""

import pytest
from app.enmus.note_enums import DownloadQuality
from app.enmus.task_status_enums import TaskStatus
from app.models.audio_model import AudioDownloadResult
from app.models.notes_model import NoteResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.routers import note as note_module
from app.routers.note import _run_merged_note_task


def _note(title, markdown, video_id, duration=10.0):
    return NoteResult(
        markdown=markdown,
        transcript=TranscriptResult(
            language="zh",
            full_text=f"{title} 全文",
            segments=[TranscriptSegment(0.0, 1.0, f"{title} 第一句")],
        ),
        audio_meta=AudioDownloadResult(
            file_path="",
            title=title,
            duration=duration,
            cover_url=None,
            platform="bilibili",
            video_id=video_id,
            raw_info={},
            video_path=None,
        ),
    )


class FakeGpt:
    def __init__(self):
        self.calls = []

    def polish_markdown(self, title, markdown):
        self.calls.append((title, markdown))
        return f"{markdown}\n\n<!-- polished -->"


class FakeGenerator:
    """记录状态写入与 generate 调用；generate 的返回值由 note_by_url 决定。"""

    instances: list = []
    statuses: list = []

    def __init__(self):
        FakeGenerator.instances.append(self)
        self.gpt = FakeGpt()
        self.generate_kwargs: list = []

    def _update_status(self, task_id, status, message=None, **kwargs):
        FakeGenerator.statuses.append((task_id, status, message))

    def _get_gpt(self, model_name, provider_id):
        return self.gpt

    def generate(self, **kwargs):
        self.generate_kwargs.append(kwargs)
        return note_module._TEST_NOTES.get(kwargs["video_url"])


@pytest.fixture
def env(monkeypatch, tmp_path):
    FakeGenerator.instances = []
    FakeGenerator.statuses = []
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(note_module, "NoteGenerator", FakeGenerator)
    monkeypatch.setattr(
        note_module, "_execute_note_with_retry", lambda task_id, gen, fn: fn()
    )
    saved = {}
    monkeypatch.setattr(
        note_module,
        "save_note_to_file",
        lambda task_id, note: saved.setdefault(task_id, note),
    )
    monkeypatch.setattr(note_module, "_enforce_cache_limit_in_background", lambda: None)
    monkeypatch.setattr(note_module, "_TEST_NOTES", {}, raising=False)
    return saved


def _items():
    return [
        {"url": "https://b/1", "video_id": "BV1_p1", "title": "第一集"},
        {"url": "https://b/2", "video_id": "BV1_p2", "title": "第二集"},
        {"url": "https://b/3", "video_id": "BV1_p3", "title": "第三集"},
    ]


def _run(merge_polish=False):
    return _run_merged_note_task(
        task_id="task-1",
        items=_items(),
        merge_title="我的合集",
        merge_polish=merge_polish,
        model_name="m",
        provider_id="p",
        platform="bilibili",
        quality=DownloadQuality.fast,
        link=False,
        screenshot=False,
        _format=[],
        scene=None,
        detail=None,
        extras=None,
        video_understanding=False,
        video_interval=0,
        grid_size=[],
        sampling_mode="interval",
        max_frames=60,
        frames_per_second=2,
        frame_limit_mode="total",
        ocr_assist=None,
        park_kwargs={},
    )


def test_partial_failure_merges_successes_and_lists_failures(env):
    note_module._TEST_NOTES = {
        "https://b/1": _note("第一集", "# 第一集\n正文一", "BV1_p1", 60),
        "https://b/2": None,
        "https://b/3": _note("第三集", "正文三", "BV1_p3", 30),
    }

    _run()

    saved = env["task-1"]
    assert saved is not None
    assert saved.markdown.startswith("# 我的合集")
    assert "## 1. 第一集" in saved.markdown
    assert "## 2. 第三集" in saved.markdown
    assert "## 未生成成功的视频" in saved.markdown
    assert "- 第二集（生成失败）" in saved.markdown
    assert saved.audio_meta.title == "我的合集"
    assert saved.audio_meta.duration == 90
    assert saved.audio_meta.video_id == "merged_task-1"

    final = FakeGenerator.statuses[-1]
    assert final[1] == TaskStatus.SUCCESS
    assert "2/3" in final[2]
    assert "1 个失败" in final[2]


def test_sub_generations_use_internal_ids_and_skip_metadata(env):
    note_module._TEST_NOTES = {
        "https://b/1": _note("第一集", "正文一", "BV1_p1"),
        "https://b/2": _note("第二集", "正文二", "BV1_p2"),
        "https://b/3": _note("第三集", "正文三", "BV1_p3"),
    }

    _run()

    sub_generators = [gen for gen in FakeGenerator.instances if gen.generate_kwargs]
    assert len(sub_generators) == 3
    task_ids = [gen.generate_kwargs[0]["task_id"] for gen in sub_generators]
    assert task_ids == ["task-1-s1", "task-1-s2", "task-1-s3"]
    assert all(
        gen.generate_kwargs[0]["persist_metadata"] is False for gen in sub_generators
    )


def test_all_failures_mark_the_task_failed(env):
    note_module._TEST_NOTES = {
        "https://b/1": None,
        "https://b/2": None,
        "https://b/3": None,
    }

    _run()

    assert env == {}
    final = FakeGenerator.statuses[-1]
    assert final[1] == TaskStatus.FAILED
    assert "3 个视频都没能生成" in final[2]


def test_polish_runs_only_when_requested(env):
    note_module._TEST_NOTES = {
        "https://b/1": _note("第一集", "正文一", "BV1_p1"),
        "https://b/2": _note("第二集", "正文二", "BV1_p2"),
        "https://b/3": _note("第三集", "正文三", "BV1_p3"),
    }

    _run(merge_polish=True)

    polish_calls = [gen.gpt.calls for gen in FakeGenerator.instances if gen.gpt.calls]
    assert len(polish_calls) == 1
    assert polish_calls[0][0][0] == "我的合集"
    assert env["task-1"].markdown.endswith("<!-- polished -->")
