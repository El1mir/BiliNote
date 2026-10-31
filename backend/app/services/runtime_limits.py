"""运行时限额门面（2026-10-17）。

后端有一批「应当由用户配置、但历史上硬编码」的事务参数：ASR 的输入体积/时长上限、
静音拆分开关与阈值、LLM 的请求体预算与重试策略、OCR 阶段的并发与插图上限。它们
决定的是「一次事务能做多大」，不是「业务规则」，所以放在「通用设置」里由用户调。

本模块是**唯一的读取入口**：

* 值来自 ``general_settings`` 表（用户在前端设置页改）；
* 环境变量仍然优先 —— 部署方用 env 固定一个值（如 Docker 里锁死网关上限）时，
  不该被界面上的手滑改掉；
* 读库失败、列是 NULL、值非法，一律回落到 :mod:`app.db.models.general_settings`
  里的常量，绝不抛异常（这些值在生成任务的热路径上）。

为什么带缓存：``UniversalGPT.__init__`` 与每次 ASR 调用都会读，而它们可能每秒
发生多次；每读一次就开一次 SQLite 连接既慢又会放大锁竞争。缓存 5 秒，用户在
设置页点保存后最多 5 秒生效 —— 这个延迟可以接受，且 ``reset_cache()`` 供测试与
写入路径主动失效。
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

from app.db.models.general_settings import (
    DEFAULT_ASR_MAX_DURATION_MINUTES,
    DEFAULT_ASR_MAX_FILE_MB,
    DEFAULT_ASR_MIN_SILENCE_SECONDS,
    DEFAULT_ASR_SILENCE_NOISE_DB,
    DEFAULT_ASR_SILENCE_SPLIT,
    DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
    DEFAULT_LLM_MAX_REQUEST_BYTES,
    DEFAULT_LLM_RETRY_ATTEMPTS,
    DEFAULT_LLM_RETRY_BACKOFF_SECONDS,
    DEFAULT_DOWNLOAD_RETRIES,
    DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
    DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
    DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    DEFAULT_NOTE_MAX_IMAGES,
    DEFAULT_NOTE_MAX_RETRIES,
    DEFAULT_NOTE_RETRY_BACKOFF_SECONDS,
    DEFAULT_OCR_STAGE_CONCURRENCY,
    MAX_LLM_MAX_REQUEST_BYTES,
    MAX_DOWNLOAD_RETRIES,
    MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS,
    MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS,
    MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    MAX_NOTE_MAX_IMAGES,
    MAX_NOTE_MAX_RETRIES,
    MAX_NOTE_RETRY_BACKOFF_SECONDS,
    MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    MAX_OCR_STAGE_CONCURRENCY,
    MIN_LLM_MAX_REQUEST_BYTES,
    DEFAULT_SCREENSHOT_MAX_WIDTH,
    DEFAULT_SCREENSHOT_QUALITY,
    DEFAULT_FFMPEG_TIMEOUT_SECONDS,
    DEFAULT_OCR_MAX_JUDGE_CANDIDATES,
    MAX_SCREENSHOT_MAX_WIDTH,
    MAX_SCREENSHOT_QUALITY,
    MAX_FFMPEG_TIMEOUT_SECONDS,
    MAX_OCR_MAX_JUDGE_CANDIDATES,
    MIN_SCREENSHOT_QUALITY,
    MIN_FFMPEG_TIMEOUT_SECONDS,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 缓存有效期（秒）。见模块 docstring：设置页保存后最多这么久生效。
_CACHE_TTL_SECONDS = 5.0

#: 判定层图片预算与请求体预算之间必须留出的安全距离。
_JUDGE_SAFETY_MARGIN_BYTES = 1024 * 1024

_lock = threading.Lock()
_cached: Optional[Dict[str, Any]] = None
_cached_at = 0.0

def reset_cache() -> None:
    """丢弃缓存，下一次读取重新查库。写入路径与测试用。"""
    global _cached, _cached_at
    with _lock:
        _cached = None
        _cached_at = 0.0

def _raw_settings() -> Dict[str, Any]:
    """读一次 general_settings（带 5 秒缓存）；任何异常都返回空 dict。"""
    global _cached, _cached_at
    now = time.monotonic()
    with _lock:
        if _cached is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
            return _cached
    try:
        # 延迟 import：general_settings_dao 依赖 engine，而 engine 在模块导入期
        # 会建库；把它拖到第一次真正读值时，避免与 init_db 形成导入环。
        from app.db.general_settings_dao import get_general_settings

        values = get_general_settings()
    except Exception as exc:  # noqa: BLE001 - 读不到就用默认值，绝不打断生成任务
        logger.warning("读取运行时限额失败，使用默认值：%s", exc)
        values = {}
    with _lock:
        _cached = values
        _cached_at = now
    return values

def _env_int(name: str, fallback: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return fallback
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return fallback

def _env_float(name: str, fallback: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return fallback
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return fallback

def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return fallback
    token = str(raw).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return fallback

def _value(name: str, fallback: Any) -> Any:
    """取一个字段：DB 里有值就用它，否则回落常量。"""
    raw = _raw_settings().get(name)
    if raw is None:
        return fallback
    return raw

# ---------------------------------------------------------------------------
# ASR
# ---------------------------------------------------------------------------

def asr_max_file_mb() -> int:
    """单个音频允许转写的最大体积（MB）。``0`` = 不限。"""
    value = _env_int("ASR_MAX_FILE_MB", int(_value("asr_max_file_mb", DEFAULT_ASR_MAX_FILE_MB)))
    return max(0, value)

def asr_max_duration_minutes() -> int:
    """单个音频允许转写的最大时长（分钟）。``0`` = 不限。"""
    value = _env_int(
        "ASR_MAX_DURATION_MINUTES",
        int(_value("asr_max_duration_minutes", DEFAULT_ASR_MAX_DURATION_MINUTES)),
    )
    return max(0, value)

def asr_silence_split() -> bool:
    """全局默认的静音拆分开关（端点上的同名配置优先，见 openai_asr）。"""
    return _env_bool("ASR_SILENCE_SPLIT", bool(_value("asr_silence_split", DEFAULT_ASR_SILENCE_SPLIT)))

def asr_silence_noise_db() -> float:
    return _env_float("ASR_SILENCE_NOISE_DB", float(_value("asr_silence_noise_db", DEFAULT_ASR_SILENCE_NOISE_DB)))

def asr_min_silence_seconds() -> float:
    return _env_float(
        "ASR_MIN_SILENCE_SECONDS",
        float(_value("asr_min_silence_seconds", DEFAULT_ASR_MIN_SILENCE_SECONDS)),
    )

def asr_input_violation(file_path: str) -> Optional[str]:
    """检查音频是否越过体积/时长上限；越界返回给用户看的说明，否则 None。

    放在转写入口调用：越界时应当在**本地**就拒绝，而不是把几十小时的音频
    整段丢给上游再收到一个语焉不详的 413。
    """
    max_mb = asr_max_file_mb()
    if max_mb > 0:
        try:
            size = os.path.getsize(file_path)
        except OSError:
            size = 0
        if size > max_mb * 1024 * 1024:
            return (
                f"音频体积 {size / 1024 / 1024:.1f} MB 超过上限 {max_mb} MB，"
                "请在「设置 → 通用」调高「ASR 最大文件大小」，或先切段后再转写"
            )
    max_minutes = asr_max_duration_minutes()
    if max_minutes > 0:
        from app.utils.audio_helper import probe_duration_seconds

        seconds = probe_duration_seconds(file_path)
        if seconds and seconds > max_minutes * 60:
            return (
                f"音频时长 {seconds / 60:.1f} 分钟超过上限 {max_minutes} 分钟，"
                "请在「设置 → 通用」调高「ASR 最大时长」，或先切段后再转写"
            )
    return None

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def llm_max_request_bytes() -> int:
    """单次 LLM 请求的预算（字节）。**不含**网关硬上限的收敛，收敛在调用侧做。"""
    value = _env_int(
        "OPENAI_MAX_REQUEST_BYTES",
        int(_value("llm_max_request_bytes", DEFAULT_LLM_MAX_REQUEST_BYTES)),
    )
    if value <= 0:
        return DEFAULT_LLM_MAX_REQUEST_BYTES
    return min(max(value, MIN_LLM_MAX_REQUEST_BYTES), MAX_LLM_MAX_REQUEST_BYTES)

def llm_gateway_ceiling_bytes() -> int:
    """网关硬上限（部署侧声明，默认 9 MiB）。用户配置只能**低于**它。

    为什么界面上的预算不能突破它：超限时网关直接回 413
    ``request body too large``，而 413 不在可重试清单里 —— 请求级立即失败，
    任务三次重试全废。让用户把预算调到 30 MiB 只会把失败推迟到线上。

    换成自建网关、上限确实更大的部署方，应当改环境变量
    ``OPENAI_GATEWAY_MAX_REQUEST_BYTES``（这是部署决策，不是界面偏好）。
    """
    return max(0, _env_int("OPENAI_GATEWAY_MAX_REQUEST_BYTES", 9 * 1024 * 1024))

def llm_judge_image_budget_bytes() -> int:
    """判定层留给图片的字节预算，永远显著低于当前请求体预算。"""
    budget = _env_int(
        "OPENAI_JUDGE_IMAGE_BUDGET_BYTES",
        int(_value("llm_judge_image_budget_bytes", DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES)),
    )
    # 判定层要同时低于「用户预算」和「网关上限」，再留 1 MiB 安全距离。
    effective = min(llm_max_request_bytes(), llm_gateway_ceiling_bytes())
    ceiling = max(0, effective - _JUDGE_SAFETY_MARGIN_BYTES)
    if budget <= 0:
        budget = DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES
    return min(budget, ceiling)

def llm_retry_attempts() -> int:
    """单次调用最多尝试几次（含首次）。"""
    value = _env_int(
        "OPENAI_RETRY_ATTEMPTS", int(_value("llm_retry_attempts", DEFAULT_LLM_RETRY_ATTEMPTS))
    )
    return max(1, value)

def llm_retry_backoff_seconds() -> float:
    value = _env_float(
        "OPENAI_RETRY_BACKOFF_SECONDS",
        float(_value("llm_retry_backoff_seconds", DEFAULT_LLM_RETRY_BACKOFF_SECONDS)),
    )
    return max(0.0, value)

# ---------------------------------------------------------------------------
# OCR / 插图
# ---------------------------------------------------------------------------

def ocr_stage_concurrency() -> int:
    value = _env_int(
        "OCR_STAGE_CONCURRENCY", int(_value("ocr_stage_concurrency", DEFAULT_OCR_STAGE_CONCURRENCY))
    )
    return max(1, min(value, MAX_OCR_STAGE_CONCURRENCY))

def note_max_images() -> int:
    value = _env_int("NOTE_MAX_IMAGES", int(_value("note_max_images", DEFAULT_NOTE_MAX_IMAGES)))
    return max(1, min(value, MAX_NOTE_MAX_IMAGES))

# ---------------------------------------------------------------------------
# 失败预算：任务重试 / 429 冷却 / 下载重试
# ---------------------------------------------------------------------------

def note_max_retries() -> int:
    """一条笔记任务失败后重试几次（首次之外）；0 = 不重试。

    环境变量 ``NOTE_MAX_RETRIES`` 仍然优先（老部署靠它调参，不能因为加了
    设置项就让已有的 env 静默失效）。
    """
    value = _env_int(
        "NOTE_MAX_RETRIES",
        int(_value("note_max_retries", DEFAULT_NOTE_MAX_RETRIES)),
    )
    return max(0, min(value, MAX_NOTE_MAX_RETRIES))

def note_retry_backoff_seconds() -> float:
    """重试退避基数（秒）：第 n 次等待 base * 3^(n-1)。"""
    value = _env_float(
        "NOTE_RETRY_BACKOFF_SECONDS",
        float(_value("note_retry_backoff_seconds", DEFAULT_NOTE_RETRY_BACKOFF_SECONDS)),
    )
    return max(0.0, min(value, MAX_NOTE_RETRY_BACKOFF_SECONDS))

def llm_rate_limit_cooldown_seconds() -> float:
    """撞上 429 后的全局冷却窗口（秒）。"""
    value = _env_float(
        "RATE_LIMIT_COOLDOWN_SECONDS",
        float(_value("llm_rate_limit_cooldown_seconds", DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS)),
    )
    return max(0.0, min(value, MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS))

def llm_rate_limit_max_wait_seconds() -> float:
    """429 累计等待多久后把任务交还队列（秒）。"""
    value = _env_float(
        "RATE_LIMIT_MAX_WAIT_SECONDS",
        float(_value("llm_rate_limit_max_wait_seconds", DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS)),
    )
    return max(0.0, min(value, MAX_LLM_RATE_LIMIT_MAX_WAIT_SECONDS))

def llm_rate_limit_resume_interval_seconds() -> float:
    """429 等待期间每隔多久探一次配额（秒）。"""
    value = _env_float(
        "RATE_LIMIT_RESUME_INTERVAL_SECONDS",
        float(
            _value(
                "llm_rate_limit_resume_interval_seconds",
                DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
            )
        ),
    )
    return min(
        max(value, MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS),
        MAX_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS,
    )

def download_retries() -> int:
    """下载阶段的重试次数（yt-dlp 的 retries / fragment_retries）；0 = 不重试。"""
    value = _env_int(
        "DOWNLOAD_RETRIES",
        int(_value("download_retries", DEFAULT_DOWNLOAD_RETRIES)),
    )
    return max(0, min(value, MAX_DOWNLOAD_RETRIES))

def download_socket_timeout_seconds() -> int:
    """下载阶段的 socket 超时（秒）。不允许 0 —— yt-dlp 会把它当成永不超时。"""
    value = _env_int(
        "DOWNLOAD_SOCKET_TIMEOUT_SECONDS",
        int(_value("download_socket_timeout_seconds", DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS)),
    )
    return min(
        max(value, MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS),
        MAX_DOWNLOAD_SOCKET_TIMEOUT_SECONDS,
    )

# ---------------------------------------------------------------------------
# 截图编码：决定单张图有多大，进而决定一次请求能带几张图
# ---------------------------------------------------------------------------

def screenshot_max_width() -> int:
    """截图最大宽度（像素）；``0`` = 保持原始分辨率。

    为什么要缩放：图片字节数直接决定 ``llm_max_request_bytes`` 能塞进几张图。
    4K 视频原尺寸截图一张就有几百 KB，base64 再涨 1/3，几张图就把预算吃光，
    而模型看 1280px 宽的截图与看 3840px 的几乎没有区别。
    """
    value = _env_int(
        "SCREENSHOT_MAX_WIDTH",
        int(_value("screenshot_max_width", DEFAULT_SCREENSHOT_MAX_WIDTH)),
    )
    if value <= 0:
        return 0
    return min(value, MAX_SCREENSHOT_MAX_WIDTH)

def screenshot_quality() -> int:
    """ffmpeg 的 ``-q:v``（1 最好、31 最差），夹取到 [1, 31]。"""
    value = _env_int(
        "SCREENSHOT_QUALITY",
        int(_value("screenshot_quality", DEFAULT_SCREENSHOT_QUALITY)),
    )
    return min(max(value, MIN_SCREENSHOT_QUALITY), MAX_SCREENSHOT_QUALITY)

def ffmpeg_timeout_seconds() -> int:
    """单次 ffmpeg 调用（截图/抽帧）的超时秒数，夹取到 [10, 600]。

    网络盘或长视频上 60 秒可能不够，超时会让截图静默丢失（日志里只有一行
    error，笔记里就是没有配图）。
    """
    value = _env_int(
        "FFMPEG_TIMEOUT_SECONDS",
        int(_value("ffmpeg_timeout_seconds", DEFAULT_FFMPEG_TIMEOUT_SECONDS)),
    )
    return min(max(value, MIN_FFMPEG_TIMEOUT_SECONDS), MAX_FFMPEG_TIMEOUT_SECONDS)

def ocr_max_judge_candidates() -> int:
    """一次「哪些时间点值得截图」的判定最多看多少个候选。

    候选越多，判定提示词越长，和图片抢的是同一份请求预算。
    """
    value = _env_int(
        "OCR_MAX_JUDGE_CANDIDATES",
        int(_value("ocr_max_judge_candidates", DEFAULT_OCR_MAX_JUDGE_CANDIDATES)),
    )
    return max(1, min(value, MAX_OCR_MAX_JUDGE_CANDIDATES))

# ---------------------------------------------------------------------------
# BASE_PROMPT 覆盖层（spec 005 ticket 11）
# ---------------------------------------------------------------------------

def base_prompt_override() -> str:
    """用户自定义的 BASE_PROMPT 覆盖层；空串 = 用内置模板。

    为什么放在这里而不是直接读 DAO：这是**生成热路径**上的读取（每段字幕拼一次
    提示词），必须复用本模块的 5 秒缓存，否则每生成一段就开一次 SQLite 连接。
    写入路径（update_general_settings）已经会调 reset_cache()，所以设置页保存后
    在下一个任务就能生效，不需要重启服务。

    环境变量优先：部署方用 BASE_PROMPT_OVERRIDE 固定模板时，不该被界面覆盖 ——
    与其余字段的处理一致。读到非法值/空值一律返回空串，由调用方回落到内置模板。
    """
    raw = os.getenv("BASE_PROMPT_OVERRIDE")
    if raw is not None and str(raw).strip():
        value: Any = raw
    else:
        value = _value("base_prompt_override", "")
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return text

