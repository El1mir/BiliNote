import enum
from typing import Any, Optional


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    DOWNLOADING = "DOWNLOADING"
    TRANSCRIBING = "TRANSCRIBING"
    SUMMARIZING = "SUMMARIZING"
    FORMATTING = "FORMATTING"
    SAVING = "SAVING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

    @classmethod
    def description(cls, status):
        desc_map = {
            cls.PENDING: "排队中",
            cls.PARSING: "解析链接",
            cls.DOWNLOADING: "下载中",
            cls.TRANSCRIBING: "转录中",
            cls.SUMMARIZING: "总结中",
            cls.FORMATTING: "格式化中",
            cls.SAVING: "保存中",
            cls.SUCCESS: "完成",
            cls.FAILED: "失败",
        }
        return desc_map.get(status, "未知状态")


class TaskStage(str, enum.Enum):
    QUEUED = "queued"
    PARSING = "parsing"
    FETCHING_SUBTITLES = "fetching_subtitles"
    DOWNLOADING_VIDEO = "downloading_video"
    DOWNLOADING_AUDIO = "downloading_audio"
    TRANSCRIBING = "transcribing"
    PLANNING_FRAMES = "planning_frames"
    EXTRACTING_FRAMES = "extracting_frames"
    BUILDING_GRIDS = "building_grids"
    SUMMARIZING = "summarizing"
    POST_PROCESSING = "post_processing"
    SAVING = "saving"
    SUCCESS = "success"
    FAILED = "failed"


_STAGE_LABELS = {
    TaskStage.QUEUED: "排队中",
    TaskStage.PARSING: "解析链接",
    TaskStage.FETCHING_SUBTITLES: "获取字幕",
    TaskStage.DOWNLOADING_VIDEO: "下载视频",
    TaskStage.DOWNLOADING_AUDIO: "下载音频",
    TaskStage.TRANSCRIBING: "音频转写",
    TaskStage.PLANNING_FRAMES: "规划采样",
    TaskStage.EXTRACTING_FRAMES: "抽取画面",
    TaskStage.BUILDING_GRIDS: "拼接网格图",
    TaskStage.SUMMARIZING: "生成总结",
    TaskStage.POST_PROCESSING: "整理内容",
    TaskStage.SAVING: "保存结果",
    TaskStage.SUCCESS: "已完成",
    TaskStage.FAILED: "失败",
}

# Centralize stage weights so the backend, rather than the frontend, owns global progress.
_STAGE_WEIGHTS = {
    TaskStage.QUEUED: 2,
    TaskStage.PARSING: 5,
    TaskStage.FETCHING_SUBTITLES: 8,
    TaskStage.DOWNLOADING_VIDEO: 15,
    TaskStage.DOWNLOADING_AUDIO: 10,
    TaskStage.TRANSCRIBING: 25,
    TaskStage.PLANNING_FRAMES: 8,
    TaskStage.EXTRACTING_FRAMES: 10,
    TaskStage.BUILDING_GRIDS: 7,
    TaskStage.SUMMARIZING: 7,
    TaskStage.POST_PROCESSING: 2,
    TaskStage.SAVING: 1,
}

_STATUS_TO_STAGE = {
    TaskStatus.PENDING: TaskStage.QUEUED,
    TaskStatus.PARSING: TaskStage.PARSING,
    TaskStatus.DOWNLOADING: TaskStage.DOWNLOADING_AUDIO,
    TaskStatus.TRANSCRIBING: TaskStage.TRANSCRIBING,
    TaskStatus.SUMMARIZING: TaskStage.SUMMARIZING,
    TaskStatus.FORMATTING: TaskStage.POST_PROCESSING,
    TaskStatus.SAVING: TaskStage.SAVING,
    TaskStatus.SUCCESS: TaskStage.SUCCESS,
    TaskStatus.FAILED: TaskStage.FAILED,
}


def stage_label(stage: TaskStage | str) -> str:
    try:
        stage = TaskStage(stage)
    except (TypeError, ValueError):
        return "处理中"
    return _STAGE_LABELS.get(stage, "处理中")


def stage_for_status(status: TaskStatus | str) -> TaskStage:
    try:
        status = TaskStatus(status)
    except (TypeError, ValueError):
        return TaskStage.QUEUED
    return _STATUS_TO_STAGE.get(status, TaskStage.QUEUED)


def global_progress(stage: TaskStage | str, stage_progress: Optional[float] = None) -> Optional[int]:
    """Calculate a weighted percentage without inventing unknown stage progress."""
    try:
        stage = TaskStage(stage)
    except (TypeError, ValueError):
        return None
    if stage == TaskStage.SUCCESS:
        return 100
    if stage == TaskStage.FAILED or stage not in _STAGE_WEIGHTS:
        return None
    ordered = list(_STAGE_WEIGHTS)
    completed = sum(_STAGE_WEIGHTS[item] for item in ordered[:ordered.index(stage)])
    current = _STAGE_WEIGHTS[stage]
    if stage_progress is None:
        return round(completed / sum(_STAGE_WEIGHTS.values()) * 100)
    bounded = max(0.0, min(100.0, float(stage_progress)))
    return round((completed + current * bounded / 100) / sum(_STAGE_WEIGHTS.values()) * 100)


def normalize_progress(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None
