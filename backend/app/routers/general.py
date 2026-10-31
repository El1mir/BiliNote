# app/routers/general.py
"""General settings and globally active LLM selection."""

from app.db.general_settings_dao import get_general_settings, update_general_settings
from app.services.active_model import (
    get_active_model,
    list_global_model_options,
    set_active_model,
)
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R
from fastapi import APIRouter
from pydantic import BaseModel

logger = get_logger(__name__)
router = APIRouter(prefix="/general", tags=["general"])


class GeneralSettingsRequest(BaseModel):
    """部分更新请求体：**只有出现在请求里的字段**才会被改写。

    ``None`` 与「没传」在 pydantic 里是同一件事（字段默认值即 None），所以本接口
    不表达「清空某字段」—— 这正符合语义：每个字段都有自己的合法下界，没有空值状态。
    """

    max_parallel_notes: int | None = None
    cache_limit_bytes: int | None = None
    min_free_disk_bytes: int | None = None
    circuit_breaker_threshold: int | None = None

    # 2026-10-17：ASR 输入上限 + 静音拆分 + LLM 请求体预算 + OCR 阶段参数。
    # 类型与模型列一致（布尔在库里存 0/1，但接口上仍然是真正的 bool）。
    asr_max_file_mb: int | None = None
    asr_max_duration_minutes: int | None = None
    asr_silence_split: bool | None = None
    asr_silence_noise_db: float | None = None
    asr_min_silence_seconds: float | None = None
    llm_max_request_bytes: int | None = None
    llm_judge_image_budget_bytes: int | None = None
    llm_retry_attempts: int | None = None
    llm_retry_backoff_seconds: float | None = None
    ocr_stage_concurrency: int | None = None
    note_max_images: int | None = None

    # 2026-10-17 第二轮：失败预算（任务重试 / 429 冷却 / 下载重试）。
    # 这些值原先只认环境变量，改完必须重启后端，设置页里完全看不到。
    note_max_retries: int | None = None
    note_retry_backoff_seconds: float | None = None
    llm_rate_limit_cooldown_seconds: float | None = None
    llm_rate_limit_max_wait_seconds: float | None = None
    llm_rate_limit_resume_interval_seconds: float | None = None
    download_retries: int | None = None
    download_socket_timeout_seconds: int | None = None

    # 2026-10-17 第三轮：截图编码与 ffmpeg 超时。这几项决定「一张图有多大」，
    # 也就是 llm_max_request_bytes 的真实可用容量。
    screenshot_max_width: int | None = None
    screenshot_quality: int | None = None
    ffmpeg_timeout_seconds: int | None = None
    ocr_max_judge_candidates: int | None = None

    # 2026-10-05（spec 005 ticket 11）：BASE_PROMPT 覆盖层的编辑入口。
    # 传空串 = 恢复内置模板；这一项是本模块唯一允许「用空值表达清空」的字段，
    # 因为空串有明确语义（没覆盖），而不是像数值字段那样有各自的合法下界。
    base_prompt_override: str | None = None


class ActiveModelRequest(BaseModel):
    provider_id: str
    model_name: str


@router.get("/settings")
def read_general_settings():
    try:
        settings = get_general_settings()
        settings["active_model"] = get_active_model()
        return R.success(settings)
    except Exception as exc:
        logger.exception("读取通用设置失败")
        return R.error(f"读取通用设置失败：{exc}", code=500)


@router.post("/settings")
def write_general_settings(data: GeneralSettingsRequest):
    try:
        return R.success(
            update_general_settings(
                max_parallel_notes=data.max_parallel_notes,
                cache_limit_bytes=data.cache_limit_bytes,
                min_free_disk_bytes=data.min_free_disk_bytes,
                circuit_breaker_threshold=data.circuit_breaker_threshold,
                asr_max_file_mb=data.asr_max_file_mb,
                asr_max_duration_minutes=data.asr_max_duration_minutes,
                asr_silence_split=data.asr_silence_split,
                asr_silence_noise_db=data.asr_silence_noise_db,
                asr_min_silence_seconds=data.asr_min_silence_seconds,
                llm_max_request_bytes=data.llm_max_request_bytes,
                llm_judge_image_budget_bytes=data.llm_judge_image_budget_bytes,
                llm_retry_attempts=data.llm_retry_attempts,
                llm_retry_backoff_seconds=data.llm_retry_backoff_seconds,
                ocr_stage_concurrency=data.ocr_stage_concurrency,
                note_max_images=data.note_max_images,
                note_max_retries=data.note_max_retries,
                note_retry_backoff_seconds=data.note_retry_backoff_seconds,
                llm_rate_limit_cooldown_seconds=data.llm_rate_limit_cooldown_seconds,
                llm_rate_limit_max_wait_seconds=data.llm_rate_limit_max_wait_seconds,
                llm_rate_limit_resume_interval_seconds=data.llm_rate_limit_resume_interval_seconds,
                download_retries=data.download_retries,
                download_socket_timeout_seconds=data.download_socket_timeout_seconds,
                screenshot_max_width=data.screenshot_max_width,
                screenshot_quality=data.screenshot_quality,
                ffmpeg_timeout_seconds=data.ffmpeg_timeout_seconds,
                ocr_max_judge_candidates=data.ocr_max_judge_candidates,
                base_prompt_override=data.base_prompt_override,
            )
        )
    except Exception as exc:
        logger.exception("保存通用设置失败")
        return R.error(f"保存通用设置失败：{exc}", code=500)


@router.post("/active_model")
def activate_model(data: ActiveModelRequest):
    try:
        return R.success(set_active_model(data.provider_id, data.model_name))
    except ValueError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("激活 LLM 模型失败")
        return R.error(f"激活 LLM 模型失败：{exc}", code=500)


@router.get("/active_model/options")
def read_active_model_options():
    """全局模型的候选：启用供应商 × 其下模型（spec 019）。

    选择器住在「模型提供商」页，所以候选也只来自那里 —— 停用的供应商、被删掉的
    模型不会出现在列表里，选不到也就不可能再存下一个失效指针。
    """
    try:
        return R.success(list_global_model_options())
    except Exception as exc:
        logger.exception("读取全局模型候选失败")
        return R.error(f"读取全局模型候选失败：{exc}", code=500)
