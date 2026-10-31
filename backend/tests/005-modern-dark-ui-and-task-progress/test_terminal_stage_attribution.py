"""spec 005 ticket 08：终态也带上「哪一步」。

历史缺陷：SUCCESS 一律写 stage='success'、FAILED 一律写 stage='failed'，
于是前端拿到的阶段序列在终态时退化成两个聚合值 —— 12 个阶段在成功后全显示
待处理，失败后也看不出失败发生在哪一步。

这里固定三件事：在途阶段被记住、终态继承它、跨实例（路由层新建
NoteGenerator() 写终态）也能从状态注册表读回。
"""
import pytest

from app.enmus.task_status_enums import TaskStage, TaskStatus
from app.services import task_status_cache
from app.services.note import NoteGenerator


def _bare_generator():
    """不走 __init__：它要建转写器，与本用例无关。"""
    generator = object.__new__(NoteGenerator)
    generator._in_flight_stage = None
    return generator


@pytest.fixture(autouse=True)
def _isolated_output(tmp_path, monkeypatch):
    from app.services import note as note_module

    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp_path)
    task_status_cache.clear()
    yield
    task_status_cache.clear()


def test_success_keeps_the_last_in_flight_stage():
    generator = _bare_generator()
    generator._update_status("task-success", TaskStatus.SAVING, stage=TaskStage.SAVING)
    generator._update_status("task-success", TaskStatus.SUCCESS)

    payload = task_status_cache.get("task-success")
    assert payload["status"] == TaskStatus.SUCCESS.value
    assert payload["stage"] == TaskStage.SAVING.value
    assert payload["stage_label"] == "保存结果"
    assert payload["progress"] == 100


def test_failure_keeps_the_stage_that_broke():
    generator = _bare_generator()
    generator._update_status("task-fail", TaskStatus.TRANSCRIBING, stage=TaskStage.TRANSCRIBING)
    generator._update_status("task-fail", TaskStatus.FAILED, message="转写服务超时")

    payload = task_status_cache.get("task-fail")
    assert payload["stage"] == TaskStage.TRANSCRIBING.value
    assert payload["message"] == "转写服务超时"
    # 失败时保留的是「走到哪一步」的真实完成度（TRANSCRIBING 之前的权重合计），
    # 不是伪造 100，也不是 None —— 前端据此能把进度条停在出错的位置。
    assert payload["progress"] == 40


def test_cross_instance_terminal_write_recovers_the_stage_from_the_registry():
    worker = _bare_generator()
    worker._update_status("task-cross", TaskStatus.DOWNLOADING, stage=TaskStage.DOWNLOADING_VIDEO)

    # 路由层的熔断/合并收尾/恢复路径都是新建实例写终态，实例字段是空的。
    other = _bare_generator()
    other._update_status("task-cross", TaskStatus.FAILED, message="熔断")

    payload = task_status_cache.get("task-cross")
    assert payload["stage"] == TaskStage.DOWNLOADING_VIDEO.value


def test_terminal_write_without_history_falls_back_to_the_status_mapping():
    generator = _bare_generator()
    generator._update_status("task-cold", TaskStatus.SUCCESS)

    payload = task_status_cache.get("task-cold")
    assert payload["stage"] == TaskStage.SUCCESS.value
    assert payload["progress"] == 100


def test_detail_is_always_a_mapping():
    generator = _bare_generator()
    generator._update_status(
        "task-detail",
        TaskStatus.DOWNLOADING,
        stage=TaskStage.EXTRACTING_FRAMES,
        stage_progress=50,
        detail={"current": 12, "total": 24, "unit": "frames"},
    )

    payload = task_status_cache.get("task-detail")
    assert payload["detail"] == {"current": 12, "total": 24, "unit": "frames"}
    assert payload["stage_label"] == "抽取画面"


def test_missing_detail_is_an_empty_mapping_not_none():
    generator = _bare_generator()
    generator._update_status("task-nodetail", TaskStatus.PARSING, stage=TaskStage.PARSING)

    assert task_status_cache.get("task-nodetail")["detail"] == {}