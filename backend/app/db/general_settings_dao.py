"""通用设置的读写（spec 007；缓存边界字段见 spec 009 / ticket 07）。

单行表：不存在就建，存在就更新。读不到时一律回落到默认值，绝不抛异常 ——
这个值决定「同时能跑几个笔记任务」，读失败必须退化到保守的默认值而不是让
生成入口整个挂掉。同样的理由适用于 ticket 07 新增的三个缓存边界字段：它们
决定媒体清理和熔断行为，读不到数据库时必须各自回落默认值，而不是 500。
"""

from __future__ import annotations

from typing import Any

from app.db.engine import get_db
from app.db.models.general_settings import (
    DEFAULT_ASR_MAX_DURATION_MINUTES,
    DEFAULT_ASR_MAX_FILE_MB,
    DEFAULT_ASR_MIN_SILENCE_SECONDS,
    DEFAULT_ASR_SILENCE_NOISE_DB,
    DEFAULT_ASR_SILENCE_SPLIT,
    DEFAULT_CACHE_LIMIT_BYTES,
    DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    DEFAULT_DOWNLOAD_RETRIES,
    DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    DEFAULT_FFMPEG_TIMEOUT_SECONDS,
    DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
    DEFAULT_LLM_MAX_REQUEST_BYTES,
    DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
    DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
    DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    DEFAULT_LLM_RETRY_ATTEMPTS,
    DEFAULT_LLM_RETRY_BACKOFF_SECONDS,
    DEFAULT_MAX_PARALLEL_NOTES,
    DEFAULT_MIN_FREE_DISK_BYTES,
    DEFAULT_NOTE_MAX_IMAGES,
    DEFAULT_NOTE_MAX_RETRIES,
    DEFAULT_NOTE_RETRY_BACKOFF_SECONDS,
    DEFAULT_OCR_MAX_JUDGE_CANDIDATES,
    DEFAULT_OCR_STAGE_CONCURRENCY,
    DEFAULT_SCREENSHOT_MAX_WIDTH,
    DEFAULT_SCREENSHOT_QUALITY,
    MAX_ASR_MAX_DURATION_MINUTES,
    MAX_ASR_MAX_FILE_MB,
    MAX_ASR_MIN_SILENCE_SECONDS,
    MAX_ASR_SILENCE_NOISE_DB,
    MAX_CACHE_LIMIT_BYTES,
    MAX_CIRCUIT_BREAKER_THRESHOLD,
    MAX_DOWNLOAD_RETRIES,
    MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    MAX_FFMPEG_TIMEOUT_SECONDS,
    MAX_LLM_MAX_REQUEST_BYTES,
    MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
    MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
    MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    MAX_LLM_RETRY_ATTEMPTS,
    MAX_LLM_RETRY_BACKOFF_SECONDS,
    MAX_MIN_FREE_DISK_BYTES,
    MAX_NOTE_MAX_IMAGES,
    MAX_NOTE_MAX_RETRIES,
    MAX_NOTE_RETRY_BACKOFF_SECONDS,
    MAX_OCR_MAX_JUDGE_CANDIDATES,
    MAX_OCR_STAGE_CONCURRENCY,
    MAX_PARALLEL_NOTES_LIMIT,
    MAX_SCREENSHOT_MAX_WIDTH,
    MAX_SCREENSHOT_QUALITY,
    MIN_ASR_MIN_SILENCE_SECONDS,
    MIN_ASR_SILENCE_NOISE_DB,
    MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    MIN_FFMPEG_TIMEOUT_SECONDS,
    MIN_LLM_MAX_REQUEST_BYTES,
    MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    MIN_SCREENSHOT_QUALITY,
    MAX_BASE_PROMPT_OVERRIDE_CHARS,
    REQUIRED_PROMPT_PLACEHOLDERS,
    GeneralSettings,
)
from app.gpt.prompt import BASE_PROMPT
from app.utils.logger import get_logger

logger = get_logger(__name__)


def normalize_max_parallel_notes(value: Any) -> int:
    """把任意输入收敛到 [1, MAX_PARALLEL_NOTES_LIMIT]。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PARALLEL_NOTES
    if parsed < 1:
        return 1
    return min(parsed, MAX_PARALLEL_NOTES_LIMIT)


def normalize_cache_limit_bytes(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_CACHE_LIMIT_BYTES]。

    ``0`` 是**有意义**的取值（表示「不限缓存大小」），不是「没设置」，所以
    这里不能像并行度那样把 0 抬到 1 —— 负数和垃圾输入才回落到默认的 10 GiB。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CACHE_LIMIT_BYTES
    if parsed < 0:
        return DEFAULT_CACHE_LIMIT_BYTES
    return min(parsed, MAX_CACHE_LIMIT_BYTES)


def normalize_min_free_disk_bytes(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_MIN_FREE_DISK_BYTES]。

    ``0`` = 不做磁盘门禁（用户明确要求「剩多少都照跑」）。负数是无效输入，
    回落到默认的 5 GiB —— 注意这里**不能**把负数当成 0，否则手滑输错会把
    保护静默关掉。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_FREE_DISK_BYTES
    if parsed < 0:
        return DEFAULT_MIN_FREE_DISK_BYTES
    return min(parsed, MAX_MIN_FREE_DISK_BYTES)


def normalize_circuit_breaker_threshold(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_CIRCUIT_BREAKER_THRESHOLD]。

    ``0`` = 关闭熔断（供应商一直挂也继续派发）。负数同样视为无效输入回落默认
    值 5：负数在语义上没有意义（「失败 -1 次就熔断」），当成 0 会让用户以为
    自己关掉了熔断，实际却是静默打开了默认阈值。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    if parsed < 0:
        return DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    return min(parsed, MAX_CIRCUIT_BREAKER_THRESHOLD)


def normalize_asr_max_file_mb(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_ASR_MAX_FILE_MB]。

    ``0`` = 不限体积，是**有意义的显式取值**（小内存机器、自建端点时常见），
    所以不能像并行度那样把 0 抬到 1；负数与垃圾输入才回落默认值。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ASR_MAX_FILE_MB
    if parsed < 0:
        return DEFAULT_ASR_MAX_FILE_MB
    return min(parsed, MAX_ASR_MAX_FILE_MB)


def normalize_asr_max_duration_minutes(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_ASR_MAX_DURATION_MINUTES]；``0`` = 不限时长。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_ASR_MAX_DURATION_MINUTES
    if parsed < 0:
        return DEFAULT_ASR_MAX_DURATION_MINUTES
    return min(parsed, MAX_ASR_MAX_DURATION_MINUTES)


def normalize_asr_silence_split(value: Any) -> bool:
    """把任意输入收敛成布尔。认不出来时回落默认值（开启），不抛异常。

    数据库里存的是 Integer(0/1)，JSON 请求体里可能是 ``true`` / ``"false"`` /
    ``"on"`` 等形态；这里一并吃掉，免得「前端传了字符串 → 后端当成 True」。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off"}:
            return False
    return DEFAULT_ASR_SILENCE_SPLIT


def normalize_asr_silence_noise_db(value: Any) -> float:
    """把任意输入收敛到 [MIN_ASR_SILENCE_NOISE_DB, MAX_ASR_SILENCE_NOISE_DB]。

    越界时**按边界夹取**而不是回落默认值：-90 dB 显然是「想更安静」，不是手滑，
    把它当成 -30 会让人以为设置没保存。
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ASR_SILENCE_NOISE_DB
    return min(max(parsed, MIN_ASR_SILENCE_NOISE_DB), MAX_ASR_SILENCE_NOISE_DB)


def normalize_asr_min_silence_seconds(value: Any) -> float:
    """把任意输入收敛到 [MIN_ASR_MIN_SILENCE_SECONDS, MAX_ASR_MIN_SILENCE_SECONDS]。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_ASR_MIN_SILENCE_SECONDS
    return min(max(parsed, MIN_ASR_MIN_SILENCE_SECONDS), MAX_ASR_MIN_SILENCE_SECONDS)


def normalize_llm_max_request_bytes(value: Any) -> int:
    """把任意输入收敛到 [MIN_LLM_MAX_REQUEST_BYTES, MAX_LLM_MAX_REQUEST_BYTES]。

    这里**没有**「0 = 不限」：请求体不可能无限大，0 或负数一律回落到默认 9 MiB。
    低于下限时抬到下限 —— 几百字节的预算切不出任何能用的块，只会让每个请求都
    退化成逐段发送。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_MAX_REQUEST_BYTES
    if parsed <= 0:
        return DEFAULT_LLM_MAX_REQUEST_BYTES
    return min(max(parsed, MIN_LLM_MAX_REQUEST_BYTES), MAX_LLM_MAX_REQUEST_BYTES)


def normalize_llm_judge_image_budget_bytes(value: Any) -> int:
    """把判定层图片预算收敛到 [0, MAX_LLM_MAX_REQUEST_BYTES - 1 MiB]。

    真正使用时还要再对当前请求体上限做一次 ``min``（见 runtime_limits）：这个
    函数只保证「不会超过全局最大请求体的天花板」，不保证「小于用户当前配的预算」。
    """
    ceiling = max(0, MAX_LLM_MAX_REQUEST_BYTES - 1024 * 1024)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return min(DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES, ceiling)
    if parsed < 0:
        return min(DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES, ceiling)
    return min(parsed, ceiling)


def normalize_llm_retry_attempts(value: Any) -> int:
    """把重试次数收敛到 [1, MAX_LLM_RETRY_ATTEMPTS]；1 = 不重试。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_RETRY_ATTEMPTS
    if parsed < 1:
        return 1
    return min(parsed, MAX_LLM_RETRY_ATTEMPTS)


def normalize_llm_retry_backoff_seconds(value: Any) -> float:
    """把退避基数收敛到 [0, MAX_LLM_RETRY_BACKOFF_SECONDS]；0 = 不等待。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_RETRY_BACKOFF_SECONDS
    if parsed < 0:
        return 0.0
    return min(parsed, MAX_LLM_RETRY_BACKOFF_SECONDS)


def normalize_ocr_stage_concurrency(value: Any) -> int:
    """把 OCR 阶段并发收敛到 [1, MAX_OCR_STAGE_CONCURRENCY]；1 = 串行。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_OCR_STAGE_CONCURRENCY
    if parsed < 1:
        return 1
    return min(parsed, MAX_OCR_STAGE_CONCURRENCY)


def normalize_note_max_images(value: Any) -> int:
    """把单篇插图上限收敛到 [1, MAX_NOTE_MAX_IMAGES]。

    0 不是「不插图」的合法写法 —— 想不出图请关掉「视频理解 / OCR 辅助」，
    而不是把上限设成 0（那只会让判定层白跑一遍再丢掉结果）。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_NOTE_MAX_IMAGES
    if parsed < 1:
        return 1
    return min(parsed, MAX_NOTE_MAX_IMAGES)


def _get_or_create(db) -> GeneralSettings:
    from app.db.engine import get_engine
    from app.db.init_db import init_db

    if db.get_bind() is get_engine():
        init_db()
    # pi-lens-ignore: python-sql-injection
    row = db.query(GeneralSettings).filter_by(id=1).first()
    if row is None:
        row = GeneralSettings(id=1, max_parallel_notes=DEFAULT_MAX_PARALLEL_NOTES)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _serialize(row: GeneralSettings) -> dict[str, Any]:
    """把单行设置摊平成响应 dict。

    每个可调字段都同时返回「当前值」和「上限 / 默认值」，前端不用把常量再抄
    一遍（抄了就会跟后端漂移）。所有值都过 normalize：老库里这三列可能是 NULL
    （ALTER TABLE 加的列、或者迁移前写入的行），normalize 负责把 None 变成默认值。
    """
    return {
        "max_parallel_notes": normalize_max_parallel_notes(row.max_parallel_notes),
        "max_parallel_notes_limit": MAX_PARALLEL_NOTES_LIMIT,
        "cache_limit_bytes": normalize_cache_limit_bytes(row.cache_limit_bytes),
        "cache_limit_bytes_default": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_limit": MAX_CACHE_LIMIT_BYTES,
        "min_free_disk_bytes": normalize_min_free_disk_bytes(row.min_free_disk_bytes),
        "min_free_disk_bytes_default": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_limit": MAX_MIN_FREE_DISK_BYTES,
        "circuit_breaker_threshold": normalize_circuit_breaker_threshold(
            row.circuit_breaker_threshold
        ),
        "circuit_breaker_threshold_default": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_limit": MAX_CIRCUIT_BREAKER_THRESHOLD,
        # 2026-10-17 新增：ASR 输入上限 / 静音拆分 / LLM 请求体预算 / OCR 阶段。
        # 形状与上面几个字段一致：值 + default（+ limit / min / max）。前端据此
        # 渲染输入框的上下界，不用把常量再抄一遍。
        "asr_max_file_mb": normalize_asr_max_file_mb(row.asr_max_file_mb),
        "asr_max_file_mb_default": DEFAULT_ASR_MAX_FILE_MB,
        "asr_max_file_mb_limit": MAX_ASR_MAX_FILE_MB,
        "asr_max_duration_minutes": normalize_asr_max_duration_minutes(
            row.asr_max_duration_minutes
        ),
        "asr_max_duration_minutes_default": DEFAULT_ASR_MAX_DURATION_MINUTES,
        "asr_max_duration_minutes_limit": MAX_ASR_MAX_DURATION_MINUTES,
        "asr_silence_split": normalize_asr_silence_split(row.asr_silence_split),
        "asr_silence_split_default": DEFAULT_ASR_SILENCE_SPLIT,
        "asr_silence_noise_db": normalize_asr_silence_noise_db(
            row.asr_silence_noise_db
        ),
        "asr_silence_noise_db_default": DEFAULT_ASR_SILENCE_NOISE_DB,
        "asr_silence_noise_db_min": MIN_ASR_SILENCE_NOISE_DB,
        "asr_silence_noise_db_max": MAX_ASR_SILENCE_NOISE_DB,
        "asr_min_silence_seconds": normalize_asr_min_silence_seconds(
            row.asr_min_silence_seconds
        ),
        "asr_min_silence_seconds_default": DEFAULT_ASR_MIN_SILENCE_SECONDS,
        "asr_min_silence_seconds_min": MIN_ASR_MIN_SILENCE_SECONDS,
        "asr_min_silence_seconds_max": MAX_ASR_MIN_SILENCE_SECONDS,
        "llm_max_request_bytes": normalize_llm_max_request_bytes(
            row.llm_max_request_bytes
        ),
        "llm_max_request_bytes_default": DEFAULT_LLM_MAX_REQUEST_BYTES,
        "llm_max_request_bytes_min": MIN_LLM_MAX_REQUEST_BYTES,
        "llm_max_request_bytes_max": MAX_LLM_MAX_REQUEST_BYTES,
        "llm_judge_image_budget_bytes": normalize_llm_judge_image_budget_bytes(
            row.llm_judge_image_budget_bytes
        ),
        "llm_judge_image_budget_bytes_default": DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
        "llm_retry_attempts": normalize_llm_retry_attempts(row.llm_retry_attempts),
        "llm_retry_attempts_default": DEFAULT_LLM_RETRY_ATTEMPTS,
        "llm_retry_attempts_limit": MAX_LLM_RETRY_ATTEMPTS,
        "llm_retry_backoff_seconds": normalize_llm_retry_backoff_seconds(
            row.llm_retry_backoff_seconds
        ),
        "llm_retry_backoff_seconds_default": DEFAULT_LLM_RETRY_BACKOFF_SECONDS,
        "llm_retry_backoff_seconds_limit": MAX_LLM_RETRY_BACKOFF_SECONDS,
        "ocr_stage_concurrency": normalize_ocr_stage_concurrency(
            row.ocr_stage_concurrency
        ),
        "ocr_stage_concurrency_default": DEFAULT_OCR_STAGE_CONCURRENCY,
        "ocr_stage_concurrency_limit": MAX_OCR_STAGE_CONCURRENCY,
        "note_max_images": normalize_note_max_images(row.note_max_images),
        "note_max_images_default": DEFAULT_NOTE_MAX_IMAGES,
        "note_max_images_limit": MAX_NOTE_MAX_IMAGES,
        "note_max_retries": normalize_note_max_retries(row.note_max_retries),
        "note_max_retries_default": DEFAULT_NOTE_MAX_RETRIES,
        "note_max_retries_limit": MAX_NOTE_MAX_RETRIES,
        "note_retry_backoff_seconds": normalize_note_retry_backoff_seconds(
            row.note_retry_backoff_seconds
        ),
        "note_retry_backoff_seconds_default": DEFAULT_NOTE_RETRY_BACKOFF_SECONDS,
        "note_retry_backoff_seconds_limit": MAX_NOTE_RETRY_BACKOFF_SECONDS,
        "llm_rate_limit_cooldown_seconds": normalize_llm_rate_limit_cooldown_seconds(
            row.llm_rate_limit_cooldown_seconds
        ),
        "llm_rate_limit_cooldown_seconds_default": DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
        "llm_rate_limit_cooldown_seconds_limit": MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
        "llm_rate_limit_max_wait_seconds": normalize_llm_rate_limit_max_wait_seconds(
            row.llm_rate_limit_max_wait_seconds
        ),
        "llm_rate_limit_max_wait_seconds_default": DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        "llm_rate_limit_max_wait_seconds_limit": MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        "llm_rate_limit_resume_interval_seconds": normalize_llm_rate_limit_resume_interval_seconds(
            row.llm_rate_limit_resume_interval_seconds
        ),
        "llm_rate_limit_resume_interval_seconds_default": DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "llm_rate_limit_resume_interval_seconds_min": MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "llm_rate_limit_resume_interval_seconds_max": MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "download_retries": normalize_download_retries(row.download_retries),
        "download_retries_default": DEFAULT_DOWNLOAD_RETRIES,
        "download_retries_limit": MAX_DOWNLOAD_RETRIES,
        "download_socket_timeout_seconds": normalize_download_socket_timeout_seconds(
            row.download_socket_timeout_seconds
        ),
        "download_socket_timeout_seconds_default": DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "download_socket_timeout_seconds_min": MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "download_socket_timeout_seconds_max": MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "screenshot_max_width": normalize_screenshot_max_width(
            row.screenshot_max_width
        ),
        "screenshot_max_width_default": DEFAULT_SCREENSHOT_MAX_WIDTH,
        "screenshot_max_width_limit": MAX_SCREENSHOT_MAX_WIDTH,
        "screenshot_quality": normalize_screenshot_quality(row.screenshot_quality),
        "screenshot_quality_default": DEFAULT_SCREENSHOT_QUALITY,
        "screenshot_quality_min": MIN_SCREENSHOT_QUALITY,
        "screenshot_quality_max": MAX_SCREENSHOT_QUALITY,
        "ffmpeg_timeout_seconds": normalize_ffmpeg_timeout_seconds(
            row.ffmpeg_timeout_seconds
        ),
        "ffmpeg_timeout_seconds_default": DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        "ffmpeg_timeout_seconds_min": MIN_FFMPEG_TIMEOUT_SECONDS,
        "ffmpeg_timeout_seconds_max": MAX_FFMPEG_TIMEOUT_SECONDS,
        "ocr_max_judge_candidates": normalize_ocr_max_judge_candidates(
            row.ocr_max_judge_candidates
        ),
        "ocr_max_judge_candidates_default": DEFAULT_OCR_MAX_JUDGE_CANDIDATES,
        "ocr_max_judge_candidates_limit": MAX_OCR_MAX_JUDGE_CANDIDATES,

        # 2026-10-05（spec 005 ticket 11）：BASE_PROMPT 覆盖层。空串 = 用内置模板。
        # 同时下发内置模板原文与占位符要求，前端不用把 prompt.py 里的散文抄一遍。
        "base_prompt_override": normalize_base_prompt_override(row.base_prompt_override),
        "base_prompt_default": BASE_PROMPT,
        "base_prompt_override_limit": MAX_BASE_PROMPT_OVERRIDE_CHARS,
        "base_prompt_required_placeholders": list(REQUIRED_PROMPT_PLACEHOLDERS),
        "active_provider_id": str(row.active_provider_id)
        if row.active_provider_id is not None
        else None,
        "active_model_name": row.active_model_name,
    }


def _default_payload() -> dict[str, Any]:
    """读库失败时的兜底响应，形状必须与 _serialize 完全一致。"""
    return {
        "max_parallel_notes": DEFAULT_MAX_PARALLEL_NOTES,
        "max_parallel_notes_limit": MAX_PARALLEL_NOTES_LIMIT,
        "cache_limit_bytes": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_default": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_limit": MAX_CACHE_LIMIT_BYTES,
        "min_free_disk_bytes": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_default": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_limit": MAX_MIN_FREE_DISK_BYTES,
        "circuit_breaker_threshold": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_default": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_limit": MAX_CIRCUIT_BREAKER_THRESHOLD,
        "asr_max_file_mb": DEFAULT_ASR_MAX_FILE_MB,
        "asr_max_file_mb_default": DEFAULT_ASR_MAX_FILE_MB,
        "asr_max_file_mb_limit": MAX_ASR_MAX_FILE_MB,
        "asr_max_duration_minutes": DEFAULT_ASR_MAX_DURATION_MINUTES,
        "asr_max_duration_minutes_default": DEFAULT_ASR_MAX_DURATION_MINUTES,
        "asr_max_duration_minutes_limit": MAX_ASR_MAX_DURATION_MINUTES,
        "asr_silence_split": DEFAULT_ASR_SILENCE_SPLIT,
        "asr_silence_split_default": DEFAULT_ASR_SILENCE_SPLIT,
        "asr_silence_noise_db": DEFAULT_ASR_SILENCE_NOISE_DB,
        "asr_silence_noise_db_default": DEFAULT_ASR_SILENCE_NOISE_DB,
        "asr_silence_noise_db_min": MIN_ASR_SILENCE_NOISE_DB,
        "asr_silence_noise_db_max": MAX_ASR_SILENCE_NOISE_DB,
        "asr_min_silence_seconds": DEFAULT_ASR_MIN_SILENCE_SECONDS,
        "asr_min_silence_seconds_default": DEFAULT_ASR_MIN_SILENCE_SECONDS,
        "asr_min_silence_seconds_min": MIN_ASR_MIN_SILENCE_SECONDS,
        "asr_min_silence_seconds_max": MAX_ASR_MIN_SILENCE_SECONDS,
        "llm_max_request_bytes": DEFAULT_LLM_MAX_REQUEST_BYTES,
        "llm_max_request_bytes_default": DEFAULT_LLM_MAX_REQUEST_BYTES,
        "llm_max_request_bytes_min": MIN_LLM_MAX_REQUEST_BYTES,
        "llm_max_request_bytes_max": MAX_LLM_MAX_REQUEST_BYTES,
        "llm_judge_image_budget_bytes": DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
        "llm_judge_image_budget_bytes_default": DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
        "llm_retry_attempts": DEFAULT_LLM_RETRY_ATTEMPTS,
        "llm_retry_attempts_default": DEFAULT_LLM_RETRY_ATTEMPTS,
        "llm_retry_attempts_limit": MAX_LLM_RETRY_ATTEMPTS,
        "llm_retry_backoff_seconds": DEFAULT_LLM_RETRY_BACKOFF_SECONDS,
        "llm_retry_backoff_seconds_default": DEFAULT_LLM_RETRY_BACKOFF_SECONDS,
        "llm_retry_backoff_seconds_limit": MAX_LLM_RETRY_BACKOFF_SECONDS,
        "ocr_stage_concurrency": DEFAULT_OCR_STAGE_CONCURRENCY,
        "ocr_stage_concurrency_default": DEFAULT_OCR_STAGE_CONCURRENCY,
        "ocr_stage_concurrency_limit": MAX_OCR_STAGE_CONCURRENCY,
        "note_max_images": DEFAULT_NOTE_MAX_IMAGES,
        "note_max_images_default": DEFAULT_NOTE_MAX_IMAGES,
        "note_max_images_limit": MAX_NOTE_MAX_IMAGES,
        "note_max_retries": DEFAULT_NOTE_MAX_RETRIES,
        "note_max_retries_default": DEFAULT_NOTE_MAX_RETRIES,
        "note_max_retries_limit": MAX_NOTE_MAX_RETRIES,
        "note_retry_backoff_seconds": DEFAULT_NOTE_RETRY_BACKOFF_SECONDS,
        "note_retry_backoff_seconds_default": DEFAULT_NOTE_RETRY_BACKOFF_SECONDS,
        "note_retry_backoff_seconds_limit": MAX_NOTE_RETRY_BACKOFF_SECONDS,
        "llm_rate_limit_cooldown_seconds": DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
        "llm_rate_limit_cooldown_seconds_default": DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
        "llm_rate_limit_cooldown_seconds_limit": MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
        "llm_rate_limit_max_wait_seconds": DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        "llm_rate_limit_max_wait_seconds_default": DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        "llm_rate_limit_max_wait_seconds_limit": MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
        "llm_rate_limit_resume_interval_seconds": DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "llm_rate_limit_resume_interval_seconds_default": DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "llm_rate_limit_resume_interval_seconds_min": MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "llm_rate_limit_resume_interval_seconds_max": MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
        "download_retries": DEFAULT_DOWNLOAD_RETRIES,
        "download_retries_default": DEFAULT_DOWNLOAD_RETRIES,
        "download_retries_limit": MAX_DOWNLOAD_RETRIES,
        "download_socket_timeout_seconds": DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "download_socket_timeout_seconds_default": DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "download_socket_timeout_seconds_min": MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "download_socket_timeout_seconds_max": MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
        "screenshot_max_width": DEFAULT_SCREENSHOT_MAX_WIDTH,
        "screenshot_max_width_default": DEFAULT_SCREENSHOT_MAX_WIDTH,
        "screenshot_max_width_limit": MAX_SCREENSHOT_MAX_WIDTH,
        "screenshot_quality": DEFAULT_SCREENSHOT_QUALITY,
        "screenshot_quality_default": DEFAULT_SCREENSHOT_QUALITY,
        "screenshot_quality_min": MIN_SCREENSHOT_QUALITY,
        "screenshot_quality_max": MAX_SCREENSHOT_QUALITY,
        "ffmpeg_timeout_seconds": DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        "ffmpeg_timeout_seconds_default": DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        "ffmpeg_timeout_seconds_min": MIN_FFMPEG_TIMEOUT_SECONDS,
        "ffmpeg_timeout_seconds_max": MAX_FFMPEG_TIMEOUT_SECONDS,
        "ocr_max_judge_candidates": DEFAULT_OCR_MAX_JUDGE_CANDIDATES,
        "ocr_max_judge_candidates_default": DEFAULT_OCR_MAX_JUDGE_CANDIDATES,
        "ocr_max_judge_candidates_limit": MAX_OCR_MAX_JUDGE_CANDIDATES,
        "base_prompt_override": "",
        "base_prompt_default": BASE_PROMPT,
        "base_prompt_override_limit": MAX_BASE_PROMPT_OVERRIDE_CHARS,
        "base_prompt_required_placeholders": list(REQUIRED_PROMPT_PLACEHOLDERS),
        "active_provider_id": None,
        "active_model_name": None,
    }


def get_general_settings() -> dict[str, Any]:
    db = next(get_db())
    try:
        row = _get_or_create(db)
        return _serialize(row)
    except Exception as exc:  # noqa: BLE001 - 读不到就用默认值，别拖垮调用方
        logger.error("读取通用设置失败，回退到默认值：%s", exc)
        return _default_payload()
    finally:
        db.close()


def get_active_model() -> dict[str, Any]:
    settings = get_general_settings()
    return {
        "provider_id": settings.get("active_provider_id"),
        "model_name": settings.get("active_model_name"),
    }


def set_active_model(provider_id: str, model_name: str) -> dict[str, Any]:
    normalized_provider_id = str(provider_id).strip() if provider_id is not None else ""
    if not normalized_provider_id:
        raise ValueError("供应商 ID 无效")
    if not model_name.strip():
        raise ValueError("模型名不能为空")
    from app.db.model_dao import get_models_by_provider
    from app.db.provider_dao import get_provider_by_id

    provider = get_provider_by_id(normalized_provider_id)
    if provider is None or int(provider.enabled or 0) != 1:
        raise ValueError("所选供应商不存在或未启用")
    models = get_models_by_provider(normalized_provider_id)
    if not any(model.get("model_name") == model_name.strip() for model in models):
        raise ValueError("所选模型不属于该供应商")

    db = next(get_db())
    try:
        row = _get_or_create(db)
        row.active_provider_id = normalized_provider_id
        row.active_model_name = model_name.strip()
        db.commit()
        db.refresh(row)
        return _serialize(row)
    finally:
        db.close()


def clear_active_model() -> bool:
    """清空全局模型指针；返回是否真的清掉了内容。

    只在「指针已经失效」时被调用（模型被删、供应商被停用），所以这里不校验，
    只负责把两列写回 NULL —— 留着旧名字等于让任务去用一个不存在的模型。
    """
    db = next(get_db())
    try:
        row = _get_or_create(db)
        # 用 getattr/setattr 而不是直接属性访问：SQLAlchemy 的声明式列在运行时是普通
        # 属性，但静态检查看到的是 Column[str]，直接读写会被判成类型错误。常量属性名
        # 触发 B009/B010，这里是有意为之，理由同上。
        if getattr(row, "active_provider_id") is None and not getattr(  # noqa: B009
            row, "active_model_name"
        ):
            return False
        setattr(row, "active_provider_id", None)  # noqa: B010
        setattr(row, "active_model_name", None)  # noqa: B010
        db.commit()
        return True
    finally:
        db.close()


def get_max_parallel_notes() -> int:
    """只要那一个数字时的快捷方式（生成入口每个任务都要读一次）。"""
    # 走 normalize 而不是裸 int()：这个值决定并发闸门，任何异常都必须退化到
    # 默认值。get_general_settings() 已经保证返回可解析的值，normalize 是第二道保险。
    return normalize_max_parallel_notes(
        get_general_settings().get("max_parallel_notes")
    )


def normalize_note_max_retries(value: Any) -> int:
    """把任务级重试次数收敛到 [0, MAX_NOTE_MAX_RETRIES]；``0`` = 不重试。

    与 LLM 层的 ``llm_retry_attempts`` 不是一回事：那个重试的是**单次请求**
    （毫秒到秒级），这个重试的是**整条流水线**（重下载、重转写、重调模型，
    一次可能是十分钟和一笔 token）。所以这里允许 0（一次就放弃）。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_NOTE_MAX_RETRIES
    if parsed < 0:
        return DEFAULT_NOTE_MAX_RETRIES
    return min(parsed, MAX_NOTE_MAX_RETRIES)


def normalize_note_retry_backoff_seconds(value: Any) -> float:
    """重试退避基数，收敛到 [0, MAX_NOTE_RETRY_BACKOFF_SECONDS]；0 = 不等待。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_NOTE_RETRY_BACKOFF_SECONDS
    if parsed < 0:
        return 0.0
    return min(parsed, MAX_NOTE_RETRY_BACKOFF_SECONDS)


def normalize_llm_rate_limit_cooldown_seconds(value: Any) -> float:
    """429 全局冷却窗口，收敛到 [0, MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS]。

    ``0`` = 撞上 429 后不额外停等（仍受退避控制）。负数回落默认值 —— 负数在
    语义上没有意义，当成 0 会静默关掉「所有请求一起停」这个关键保护。
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS
    if parsed < 0:
        return DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS
    return min(parsed, MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS)


def normalize_llm_rate_limit_max_wait_seconds(value: Any) -> float:
    """429 累计等待上限，收敛到 [0, MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS]。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS
    if parsed < 0:
        return DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS
    return min(parsed, MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS)


def normalize_llm_rate_limit_resume_interval_seconds(value: Any) -> float:
    """429 期间的探测间隔，夹取到 [MIN_, MAX_]。

    这里**夹取**而不是回落默认值：用户填 1 秒是「想尽快恢复」，意图明确；
    但 1 秒一次探测本身就会把限流撞回去，所以抬到下限而不是改成 300 秒。
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS
    return min(
        max(parsed, MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS),
        MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    )


def normalize_download_retries(value: Any) -> int:
    """下载重试次数，收敛到 [0, MAX_DOWNLOAD_RETRIES]；``0`` = 一次就放弃。

    允许 0 是有意的：B 站反爬触发时连续重试只会让 IP 更可疑，用户可能希望
    「失败就停，我自己换 cookie 再重来」。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DOWNLOAD_RETRIES
    if parsed < 0:
        return DEFAULT_DOWNLOAD_RETRIES
    return min(parsed, MAX_DOWNLOAD_RETRIES)


def normalize_download_socket_timeout_seconds(value: Any) -> int:
    """下载 socket 超时，夹取到 [MIN_, MAX_]；0 或负数抬到下限。

    为什么不能允许 0：yt-dlp 把 0 当成「永不超时」，卡住的 CDN 连接会永久
    占着 worker，任务永远停在「下载中」—— 这正是这个配置存在的理由。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS
    return min(
        max(parsed, MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS),
        MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    )


def normalize_screenshot_max_width(value: Any) -> int:
    """截图最大宽度（像素），0 = 保持原始分辨率。

    0 是合法值且必须保住：它代表「不要缩放」。这条历史路径上的默认行为就是
    原尺寸，把它当空值处理会让所有老部署的截图突然变小。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCREENSHOT_MAX_WIDTH
    if parsed <= 0:
        return 0
    return min(parsed, MAX_SCREENSHOT_MAX_WIDTH)


def normalize_screenshot_quality(value: Any) -> int:
    """ffmpeg 的 -q:v（1 最好、31 最差），夹取到 [1, 31]。

    这个值决定单张截图的字节数，而字节数决定一次请求能带几张图。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SCREENSHOT_QUALITY
    return min(max(parsed, MIN_SCREENSHOT_QUALITY), MAX_SCREENSHOT_QUALITY)


def normalize_ffmpeg_timeout_seconds(value: Any) -> int:
    """单次 ffmpeg 调用（截图/抽帧）的超时秒数，夹取到 [10, 600]。

    为什么不允许 0：subprocess.run(timeout=0) 会立刻超时，等于让所有截图
    都失败；而下限 10 秒是为了挡住「填 1 秒想快点失败」这种手滑。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FFMPEG_TIMEOUT_SECONDS
    return min(max(parsed, MIN_FFMPEG_TIMEOUT_SECONDS), MAX_FFMPEG_TIMEOUT_SECONDS)


def normalize_ocr_max_judge_candidates(value: Any) -> int:
    """一次判定最多看多少个候选时间点，夹取到 [1, 1000]。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_OCR_MAX_JUDGE_CANDIDATES
    if parsed < 1:
        return 1
    return min(parsed, MAX_OCR_MAX_JUDGE_CANDIDATES)


def normalize_base_prompt_override(value: Any) -> str:
    """用户自定义的 BASE_PROMPT 覆盖层；空串 = 用内置模板。

    三条收敛规则，各有理由：

    * **strip 后为空就是空串**（不是 None）：数据库列是 TEXT，用空串表达「没覆盖」
      比用 NULL 少一种状态，读路径也只有一条分支；
    * **必须含全部占位符**才被接受 —— generate_base_prompt 会对模板做一次
      str.format(video_title=..., segment_text=..., tags=...) 调用，缺占位符就等于
      把标题或字幕整段从提示词里删掉，模型只能凭空编；这种模板一律判无效、回落
      空串。宁可让用户看到「没保存上」，也不要静默生成一篇没有正文引用的笔记；
    * **超过上限就拒绝**（不是截断）：截断会把模板腰斩成半句话，比不接受更糟。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) > MAX_BASE_PROMPT_OVERRIDE_CHARS:
        return ""
    if not all("{" + name + "}" in text for name in REQUIRED_PROMPT_PLACEHOLDERS):
        return ""
    return text


#: 字段名 -> normalize 函数。更新时统一走这张表，避免每加一个字段就要在
#: update_general_settings 里复制一段一模一样的 ``if x is not None: setattr``。
_SETTING_NORMALIZERS = {
    "max_parallel_notes": normalize_max_parallel_notes,
    "cache_limit_bytes": normalize_cache_limit_bytes,
    "min_free_disk_bytes": normalize_min_free_disk_bytes,
    "circuit_breaker_threshold": normalize_circuit_breaker_threshold,
    "asr_max_file_mb": normalize_asr_max_file_mb,
    "asr_max_duration_minutes": normalize_asr_max_duration_minutes,
    "asr_silence_split": normalize_asr_silence_split,
    "asr_silence_noise_db": normalize_asr_silence_noise_db,
    "asr_min_silence_seconds": normalize_asr_min_silence_seconds,
    "llm_max_request_bytes": normalize_llm_max_request_bytes,
    "llm_judge_image_budget_bytes": normalize_llm_judge_image_budget_bytes,
    "llm_retry_attempts": normalize_llm_retry_attempts,
    "llm_retry_backoff_seconds": normalize_llm_retry_backoff_seconds,
    "ocr_stage_concurrency": normalize_ocr_stage_concurrency,
    "note_max_images": normalize_note_max_images,
    "note_max_retries": normalize_note_max_retries,
    "note_retry_backoff_seconds": normalize_note_retry_backoff_seconds,
    "llm_rate_limit_cooldown_seconds": normalize_llm_rate_limit_cooldown_seconds,
    "llm_rate_limit_max_wait_seconds": normalize_llm_rate_limit_max_wait_seconds,
    "llm_rate_limit_resume_interval_seconds": normalize_llm_rate_limit_resume_interval_seconds,
    "download_retries": normalize_download_retries,
    "download_socket_timeout_seconds": normalize_download_socket_timeout_seconds,
    "screenshot_max_width": normalize_screenshot_max_width,
    "screenshot_quality": normalize_screenshot_quality,
    "ffmpeg_timeout_seconds": normalize_ffmpeg_timeout_seconds,
    "ocr_max_judge_candidates": normalize_ocr_max_judge_candidates,
    "base_prompt_override": normalize_base_prompt_override,
}


def update_general_settings(
    max_parallel_notes: Any = None,
    cache_limit_bytes: Any = None,
    min_free_disk_bytes: Any = None,
    circuit_breaker_threshold: Any = None,
    asr_max_file_mb: Any = None,
    asr_max_duration_minutes: Any = None,
    asr_silence_split: Any = None,
    asr_silence_noise_db: Any = None,
    asr_min_silence_seconds: Any = None,
    llm_max_request_bytes: Any = None,
    llm_judge_image_budget_bytes: Any = None,
    llm_retry_attempts: Any = None,
    llm_retry_backoff_seconds: Any = None,
    ocr_stage_concurrency: Any = None,
    note_max_images: Any = None,
    note_max_retries: Any = None,
    note_retry_backoff_seconds: Any = None,
    llm_rate_limit_cooldown_seconds: Any = None,
    llm_rate_limit_max_wait_seconds: Any = None,
    llm_rate_limit_resume_interval_seconds: Any = None,
    download_retries: Any = None,
    download_socket_timeout_seconds: Any = None,
    screenshot_max_width: Any = None,
    screenshot_quality: Any = None,
    ffmpeg_timeout_seconds: Any = None,
    ocr_max_judge_candidates: Any = None,
    base_prompt_override: Any = None,
) -> dict[str, Any]:
    """部分更新：只有**显式传入**（非 None）的字段会被改写，其余保持原值。

    ``None`` 表示「这次没传这个字段」，不是「把它设成空」—— 前端设置页是按需
    提交的（比如只调并行度），若把未传的字段当成清空，用户改一项就会把另外三项
    悄悄重置。三个缓存边界字段的 0 值不受影响：0 是合法的显式取值，用
    ``is not None`` 判断能正确区分。
    """
    db = next(get_db())
    try:
        row = _get_or_create(db)
        # setattr 而非 row.max_parallel_notes = ...：声明式属性在类型层面是
        # Column[int]，直接赋值会被 pyright 报 reportAttributeAccessIssue。
        # 这是本仓库既有写法（见 provider_dao.py 的 update_provider）。
        # 只改**显式传入**（非 None）的字段：前端按需提交，未传的字段必须保持原值，
        # 否则用户改一项就会把其余项悄悄重置。0 / False 都是合法显式取值，
        # 用 ``is not None`` 判断能正确区分「设成 0」与「这次没传」。
        provided = {
            "max_parallel_notes": max_parallel_notes,
            "cache_limit_bytes": cache_limit_bytes,
            "min_free_disk_bytes": min_free_disk_bytes,
            "circuit_breaker_threshold": circuit_breaker_threshold,
            "asr_max_file_mb": asr_max_file_mb,
            "asr_max_duration_minutes": asr_max_duration_minutes,
            "asr_silence_split": asr_silence_split,
            "asr_silence_noise_db": asr_silence_noise_db,
            "asr_min_silence_seconds": asr_min_silence_seconds,
            "llm_max_request_bytes": llm_max_request_bytes,
            "llm_judge_image_budget_bytes": llm_judge_image_budget_bytes,
            "llm_retry_attempts": llm_retry_attempts,
            "llm_retry_backoff_seconds": llm_retry_backoff_seconds,
            "ocr_stage_concurrency": ocr_stage_concurrency,
            "note_max_images": note_max_images,
            "note_max_retries": note_max_retries,
            "note_retry_backoff_seconds": note_retry_backoff_seconds,
            "llm_rate_limit_cooldown_seconds": llm_rate_limit_cooldown_seconds,
            "llm_rate_limit_max_wait_seconds": llm_rate_limit_max_wait_seconds,
            "llm_rate_limit_resume_interval_seconds": llm_rate_limit_resume_interval_seconds,
            "download_retries": download_retries,
            "download_socket_timeout_seconds": download_socket_timeout_seconds,
            "screenshot_max_width": screenshot_max_width,
            "screenshot_quality": screenshot_quality,
            "ffmpeg_timeout_seconds": ffmpeg_timeout_seconds,
            "ocr_max_judge_candidates": ocr_max_judge_candidates,
            # 2026-10-05（spec 005 ticket 11）：BASE_PROMPT 覆盖层。空串是**合法取值**
            # （= 恢复内置模板），靠 `is not None` 区分「没传」与「传了空串」，
            # 用户点「恢复默认」正是靠传空串生效。
            "base_prompt_override": base_prompt_override,
        }
        for _field, _raw in provided.items():
            if _raw is None:
                continue
            _normalize = _SETTING_NORMALIZERS[_field]
            _value = _normalize(_raw)
            if _field == "asr_silence_split":
                # 数据库列是 Integer(0/1)：SQLite 的布尔列实际存的就是整数，
                # 这里显式转一次，避免把 Python True 写进去后读回来变成 "1"。
                _value = 1 if _value else 0
            # setattr 而非 row.<field> = ...：声明式属性在类型层面是 Column[int]，
            # 直接赋值会被 pyright 报 reportAttributeAccessIssue（本仓库既有写法）。
            setattr(row, _field, _value)
        db.commit()
        db.refresh(row)
        # 运行时限额门面有 5 秒缓存：写成功就主动失效，用户点完保存立刻生效。
        # 延迟 import 避免与 runtime_limits 形成导入环（它在函数内才 import 本模块）。
        try:
            from app.services.runtime_limits import reset_cache

            reset_cache()
        except Exception:  # noqa: BLE001 - 缓存失效失败不该让保存失败
            pass
        return _serialize(row)
    finally:
        db.close()
