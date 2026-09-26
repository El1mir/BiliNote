from app.enmus.task_status_enums import (
    TaskStage,
    TaskStatus,
    global_progress,
    normalize_progress,
    stage_for_status,
    stage_label,
)


def test_legacy_status_maps_to_stage_metadata():
    assert stage_for_status(TaskStatus.TRANSCRIBING) == TaskStage.TRANSCRIBING
    assert stage_label(TaskStage.BUILDING_GRIDS) == "拼接网格图"
    assert global_progress(TaskStage.TRANSCRIBING, 50) is not None


def test_unknown_stage_progress_is_not_fabricated():
    assert global_progress("not-a-stage", 50) is None
    assert normalize_progress(None) is None
    assert normalize_progress(120) == 100
    assert normalize_progress(-10) == 0
