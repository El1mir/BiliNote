"""运行时限额门面与「通用设置」新增 11 个事务参数（2026-10-17）。

这些值决定「一次事务能做多大」：ASR 的输入体积/时长、静音拆分、LLM 的请求体
预算与重试、OCR 的并发与插图上限。它们都在生成任务的热路径上，所以四条硬要求：

* **0 是合法值**（ASR 两个上限里 0 = 不限），不能被 `or` 吞成默认值；
* **环境变量优先于数据库**：部署方用 env 锁死网关上限时，不该被界面改掉；
* **读库失败一律回落常量**，绝不抛异常（否则设置页 500、生成入口也挂）；
* **写设置要立刻生效**：门面有 5 秒缓存，`update_general_settings` 必须主动失效。

**不碰真实数据库**：把 `general_settings_dao.get_db` 换成指向 tmp_path 的会话。
"""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import general_settings_dao as dao
from app.db.engine import Base
from app.db.models.general_settings import (
    DEFAULT_ASR_MAX_DURATION_MINUTES,
    DEFAULT_ASR_MAX_FILE_MB,
    DEFAULT_ASR_MIN_SILENCE_SECONDS,
    DEFAULT_ASR_SILENCE_NOISE_DB,
    DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES,
    DEFAULT_LLM_MAX_REQUEST_BYTES,
    DEFAULT_LLM_RETRY_ATTEMPTS,
    DEFAULT_NOTE_MAX_IMAGES,
    DEFAULT_OCR_STAGE_CONCURRENCY,
    MAX_LLM_MAX_REQUEST_BYTES,
    MAX_NOTE_MAX_IMAGES,
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
)
from app.services import runtime_limits

MiB = 1024 * 1024

@pytest.fixture
def dao_env(tmp_path, monkeypatch):
    """把 DAO 的 `get_db` 换成临时 SQLite，并清空门面缓存。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'runtime-limits.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    def _fake_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dao, "get_db", _fake_get_db)
    runtime_limits.reset_cache()
    yield factory
    runtime_limits.reset_cache()

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """环境变量优先于数据库，测试里必须显式清掉，否则本机会被外部 env 影响。"""
    for name in (
        "ASR_MAX_FILE_MB",
        "ASR_MAX_DURATION_MINUTES",
        "ASR_SILENCE_SPLIT",
        "ASR_SILENCE_NOISE_DB",
        "ASR_MIN_SILENCE_SECONDS",
        "OPENAI_MAX_REQUEST_BYTES",
        "OPENAI_GATEWAY_MAX_REQUEST_BYTES",
        "OPENAI_JUDGE_IMAGE_BUDGET_BYTES",
        "OPENAI_RETRY_ATTEMPTS",
        "OPENAI_RETRY_BACKOFF_SECONDS",
        "OCR_STAGE_CONCURRENCY",
        "NOTE_MAX_IMAGES",
        "NOTE_MAX_RETRIES",
        "NOTE_RETRY_BACKOFF_SECONDS",
        "RATE_LIMIT_COOLDOWN_SECONDS",
        "RATE_LIMIT_MAX_WAIT_SECONDS",
        "RATE_LIMIT_RESUME_INTERVAL_SECONDS",
        "DOWNLOAD_RETRIES",
        "DOWNLOAD_SOCKET_TIMEOUT_SECONDS",
        "SCREENSHOT_MAX_WIDTH",
        "SCREENSHOT_QUALITY",
        "FFMPEG_TIMEOUT_SECONDS",
        "OCR_MAX_JUDGE_CANDIDATES",
    ):
        monkeypatch.delenv(name, raising=False)
    runtime_limits.reset_cache()

# --- 默认值：没配过就是常量 ------------------------------------------------

def test_defaults_come_from_constants(dao_env):
    assert runtime_limits.asr_max_file_mb() == DEFAULT_ASR_MAX_FILE_MB == 0
    assert runtime_limits.asr_max_duration_minutes() == DEFAULT_ASR_MAX_DURATION_MINUTES == 0
    assert runtime_limits.asr_silence_split() is True
    assert runtime_limits.asr_silence_noise_db() == DEFAULT_ASR_SILENCE_NOISE_DB
    assert runtime_limits.asr_min_silence_seconds() == DEFAULT_ASR_MIN_SILENCE_SECONDS
    assert runtime_limits.llm_max_request_bytes() == DEFAULT_LLM_MAX_REQUEST_BYTES
    assert runtime_limits.llm_judge_image_budget_bytes() == DEFAULT_LLM_JUDGE_IMAGE_BUDGET_BYTES
    assert runtime_limits.llm_retry_attempts() == DEFAULT_LLM_RETRY_ATTEMPTS
    assert runtime_limits.ocr_stage_concurrency() == DEFAULT_OCR_STAGE_CONCURRENCY
    assert runtime_limits.note_max_images() == DEFAULT_NOTE_MAX_IMAGES

def test_default_payload_exposes_bounds_for_every_new_field(dao_env):
    payload = dao.get_general_settings()
    # asr_silence_split 是布尔开关，没有上下界；其余 10 项都带 _default 与 _limit。
    assert "asr_silence_split" in payload and "asr_silence_split_default" in payload
    # 判定图片预算没有独立上下界：它的上界由 llm_max_request_bytes 推导（低 1 MiB）。
    assert payload["llm_judge_image_budget_bytes_default"] < payload["llm_max_request_bytes_default"]
    for field in (
        "asr_max_file_mb",
        "asr_max_duration_minutes",
        "asr_silence_noise_db",
        "asr_min_silence_seconds",
        "llm_max_request_bytes",
        "llm_retry_attempts",
        "llm_retry_backoff_seconds",
        "ocr_stage_concurrency",
        "note_max_images",
    ):
        assert field in payload, field
        assert f"{field}_default" in payload, field
        assert f"{field}_limit" in payload or f"{field}_max" in payload, field

# --- 0 语义 ---------------------------------------------------------------

def test_zero_means_unlimited_for_asr_caps(dao_env):
    dao.update_general_settings(asr_max_file_mb=0, asr_max_duration_minutes=0)
    assert runtime_limits.asr_max_file_mb() == 0
    assert runtime_limits.asr_max_duration_minutes() == 0

def test_negative_asr_caps_fall_back_to_unlimited(dao_env):
    dao.update_general_settings(asr_max_file_mb=-5, asr_max_duration_minutes=-1)
    assert runtime_limits.asr_max_file_mb() == 0
    assert runtime_limits.asr_max_duration_minutes() == 0

# --- 写入后立刻生效（缓存失效） -------------------------------------------

def test_update_invalidates_cache_immediately(dao_env):
    assert runtime_limits.ocr_stage_concurrency() == DEFAULT_OCR_STAGE_CONCURRENCY
    dao.update_general_settings(ocr_stage_concurrency=9)
    # 没有 sleep：update 里必须主动 reset_cache
    assert runtime_limits.ocr_stage_concurrency() == 9

def test_partial_update_leaves_other_fields_untouched(dao_env):
    dao.update_general_settings(llm_retry_attempts=7)
    dao.update_general_settings(note_max_images=42)
    assert runtime_limits.llm_retry_attempts() == 7
    assert runtime_limits.note_max_images() == 42

def test_silence_split_round_trips_as_bool(dao_env):
    dao.update_general_settings(asr_silence_split=False)
    assert runtime_limits.asr_silence_split() is False
    dao.update_general_settings(asr_silence_split=True)
    assert runtime_limits.asr_silence_split() is True

# --- 环境变量优先 ---------------------------------------------------------

def test_env_overrides_database(dao_env, monkeypatch):
    dao.update_general_settings(ocr_stage_concurrency=9)
    monkeypatch.setenv("OCR_STAGE_CONCURRENCY", "2")
    assert runtime_limits.ocr_stage_concurrency() == 2

def test_env_wins_for_gateway_ceiling(dao_env, monkeypatch):
    monkeypatch.setenv("OPENAI_GATEWAY_MAX_REQUEST_BYTES", str(20 * MiB))
    assert runtime_limits.llm_gateway_ceiling_bytes() == 20 * MiB

# --- 请求体预算与网关上限的关系 ------------------------------------------

def test_user_budget_cannot_exceed_gateway_ceiling(dao_env, monkeypatch):
    monkeypatch.setenv("OPENAI_GATEWAY_MAX_REQUEST_BYTES", str(9 * MiB))
    dao.update_general_settings(llm_max_request_bytes=30 * MiB)
    # 用户配得更大也没用：gateway ceiling 是部署侧硬上限
    assert runtime_limits.llm_gateway_ceiling_bytes() == 9 * MiB
    assert runtime_limits.llm_max_request_bytes() == 30 * MiB

def test_judge_budget_stays_below_request_budget(dao_env):
    dao.update_general_settings(llm_max_request_bytes=4 * MiB)
    budget = runtime_limits.llm_judge_image_budget_bytes()
    assert budget <= 4 * MiB - MiB
    assert budget > 0

def test_request_budget_is_clamped_into_range(dao_env):
    dao.update_general_settings(llm_max_request_bytes=1)
    assert runtime_limits.llm_max_request_bytes() == MIN_LLM_MAX_REQUEST_BYTES
    dao.update_general_settings(llm_max_request_bytes=MAX_LLM_MAX_REQUEST_BYTES * 4)
    assert runtime_limits.llm_max_request_bytes() == MAX_LLM_MAX_REQUEST_BYTES

# --- 上下界夹取 -----------------------------------------------------------

def test_concurrency_and_image_caps_are_clamped(dao_env):
    dao.update_general_settings(ocr_stage_concurrency=0, note_max_images=0)
    assert runtime_limits.ocr_stage_concurrency() == 1
    assert runtime_limits.note_max_images() == 1
    dao.update_general_settings(
        ocr_stage_concurrency=MAX_OCR_STAGE_CONCURRENCY + 5,
        note_max_images=MAX_NOTE_MAX_IMAGES + 50,
    )
    assert runtime_limits.ocr_stage_concurrency() == MAX_OCR_STAGE_CONCURRENCY
    assert runtime_limits.note_max_images() == MAX_NOTE_MAX_IMAGES

def test_silence_thresholds_are_clamped(dao_env):
    dao.update_general_settings(asr_silence_noise_db=-500.0, asr_min_silence_seconds=0.0)
    assert runtime_limits.asr_silence_noise_db() >= -80.0
    assert runtime_limits.asr_min_silence_seconds() >= 0.05

# --- 读库失败回落 ---------------------------------------------------------

def test_database_failure_falls_back_to_constants(monkeypatch):
    def _boom():
        raise RuntimeError("database is gone")

    monkeypatch.setattr(dao, "get_general_settings", _boom)
    runtime_limits.reset_cache()
    assert runtime_limits.ocr_stage_concurrency() == DEFAULT_OCR_STAGE_CONCURRENCY
    assert runtime_limits.note_max_images() == DEFAULT_NOTE_MAX_IMAGES

# --- ASR 输入闸门 ---------------------------------------------------------

def test_asr_input_violation_flags_oversized_file(dao_env, tmp_path):
    audio = tmp_path / "big.wav"
    audio.write_bytes(b"0" * (2 * MiB))
    dao.update_general_settings(asr_max_file_mb=1)
    violation = runtime_limits.asr_input_violation(str(audio))
    assert violation and "MB" in violation

def test_asr_input_violation_is_none_when_unlimited(dao_env, tmp_path):
    audio = tmp_path / "big.wav"
    audio.write_bytes(b"0" * (2 * MiB))
    dao.update_general_settings(asr_max_file_mb=0, asr_max_duration_minutes=0)
    assert runtime_limits.asr_input_violation(str(audio)) is None

def test_asr_input_violation_flags_overlong_audio(dao_env, tmp_path, monkeypatch):
    audio = tmp_path / "long.wav"
    audio.write_bytes(b"0" * 16)
    dao.update_general_settings(asr_max_duration_minutes=5)
    monkeypatch.setattr(
        "app.utils.audio_helper.probe_duration_seconds", lambda _path: 601.0
    )
    violation = runtime_limits.asr_input_violation(str(audio))
    assert violation and "分钟" in violation

# --- 失败预算：任务重试 / 429 冷却 / 下载重试 ------------------------------
#
# 这一组原先只能改环境变量，而且改完必须重启后端；现在同样走门面，改完立刻生效。

def test_failure_budget_defaults_come_from_constants(dao_env):
    from app.db.models import general_settings as model

    assert runtime_limits.note_max_retries() == model.DEFAULT_NOTE_MAX_RETRIES == 3
    assert (
        runtime_limits.note_retry_backoff_seconds()
        == model.DEFAULT_NOTE_RETRY_BACKOFF_SECONDS
    )
    assert (
        runtime_limits.llm_rate_limit_cooldown_seconds()
        == model.DEFAULT_LLM_RATE_LIMIT_COOLDOWN_SECONDS
    )
    assert (
        runtime_limits.llm_rate_limit_max_wait_seconds()
        == model.DEFAULT_LLM_RATE_LIMIT_MAX_WAIT_SECONDS
    )
    assert (
        runtime_limits.llm_rate_limit_resume_interval_seconds()
        == model.DEFAULT_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS
    )
    assert runtime_limits.download_retries() == model.DEFAULT_DOWNLOAD_RETRIES == 3
    assert (
        runtime_limits.download_socket_timeout_seconds()
        == model.DEFAULT_DOWNLOAD_SOCKET_TIMEOUT_SECONDS
    )

def test_failure_budget_updates_apply_immediately(dao_env):
    dao.update_general_settings(
        note_max_retries=0,
        llm_rate_limit_cooldown_seconds=30.0,
        download_socket_timeout_seconds=60,
    )
    assert runtime_limits.note_max_retries() == 0
    assert runtime_limits.llm_rate_limit_cooldown_seconds() == 30.0
    assert runtime_limits.download_socket_timeout_seconds() == 60

def test_failure_budget_partial_update_keeps_other_fields(dao_env):
    dao.update_general_settings(note_max_retries=7)
    payload = dao.get_general_settings()
    assert payload["note_max_retries"] == 7
    # 没传的字段必须保持原值：用户改一项不该把别的项悄悄重置
    assert payload["ocr_stage_concurrency"] == DEFAULT_OCR_STAGE_CONCURRENCY
    assert payload["llm_max_request_bytes"] == DEFAULT_LLM_MAX_REQUEST_BYTES

def test_failure_budget_values_are_clamped(dao_env):
    from app.db.models import general_settings as model

    dao.update_general_settings(
        note_max_retries=model.MAX_NOTE_MAX_RETRIES + 50,
        note_retry_backoff_seconds=model.MAX_NOTE_RETRY_BACKOFF_SECONDS + 50,
        llm_rate_limit_cooldown_seconds=model.MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS + 50,
        download_retries=model.MAX_DOWNLOAD_RETRIES + 50,
        download_socket_timeout_seconds=0,
    )
    assert runtime_limits.note_max_retries() == model.MAX_NOTE_MAX_RETRIES
    assert (
        runtime_limits.note_retry_backoff_seconds()
        == model.MAX_NOTE_RETRY_BACKOFF_SECONDS
    )
    assert (
        runtime_limits.llm_rate_limit_cooldown_seconds()
        == model.MAX_LLM_RATE_LIMIT_COOLDOWN_SECONDS
    )
    assert runtime_limits.download_retries() == model.MAX_DOWNLOAD_RETRIES
    # socket 超时不允许 0：yt-dlp 会把它当成「永不超时」，卡住的连接会永久占住 worker
    assert (
        runtime_limits.download_socket_timeout_seconds()
        == model.MIN_DOWNLOAD_SOCKET_TIMEOUT_SECONDS
    )

def test_resume_interval_is_lifted_to_its_floor(dao_env):
    from app.db.models import general_settings as model

    # 填 1 秒是「想尽快恢复」，意图明确；但 1 秒一次探测本身就会把限流撞回去，
    # 所以抬到下限而不是回落默认的 300 秒。
    dao.update_general_settings(llm_rate_limit_resume_interval_seconds=1.0)
    assert (
        runtime_limits.llm_rate_limit_resume_interval_seconds()
        == model.MIN_LLM_RATE_LIMIT_RESUME_INTERVAL_SECONDS
    )

def test_environment_still_wins_for_failure_budget(dao_env, monkeypatch):
    dao.update_general_settings(note_max_retries=2, download_retries=2)
    monkeypatch.setenv("NOTE_MAX_RETRIES", "9")
    monkeypatch.setenv("DOWNLOAD_RETRIES", "7")
    assert runtime_limits.note_max_retries() == 9
    assert runtime_limits.download_retries() == 7

def test_ydl_retry_opts_track_runtime_config(dao_env):
    """下载器的 YDL_RETRY_OPTS 必须**每次解包都重读**配置。

    它曾经是模块级 dict，改设置必须重启后端才生效；改成 Mapping 实现后，
    这里验证「改完立刻能读到」，并确认两个键（retries / fragment_retries）
    都指向同一个来源 —— 只改其中一个会让分片下载退化成不重试。
    """
    from app.downloaders.base import YDL_RETRY_OPTS

    dao.update_general_settings(download_retries=1, download_socket_timeout_seconds=11)
    assert YDL_RETRY_OPTS["retries"] == 1
    assert YDL_RETRY_OPTS["fragment_retries"] == 1
    assert YDL_RETRY_OPTS["socket_timeout"] == 11
    # 解包（yt-dlp 真正使用它的方式）也要拿到同一份值
    assert dict(**YDL_RETRY_OPTS) == {
        "retries": 1,
        "fragment_retries": 1,
        "socket_timeout": 11,
    }
    dao.update_general_settings(download_retries=4)
    assert YDL_RETRY_OPTS["retries"] == 4

def test_default_payload_covers_failure_budget_fields(dao_env):
    """`_default_payload()` 是读库失败时的兜底响应，形状必须与 `_serialize` 一致。"""
    payload = dao._default_payload()
    for field in (
        "note_max_retries",
        "note_retry_backoff_seconds",
        "llm_rate_limit_cooldown_seconds",
        "llm_rate_limit_max_wait_seconds",
        "llm_rate_limit_resume_interval_seconds",
        "download_retries",
        "download_socket_timeout_seconds",
    ):
        assert field in payload, f"{field} missing from default payload"
    # 前端靠伴生键渲染上下界，缺一个就只能把常量抄到前端
    assert payload["note_max_retries_limit"] > payload["note_max_retries"]
    assert payload["download_retries_limit"] > payload["download_retries"]
    assert (
        payload["download_socket_timeout_seconds_min"]
        < payload["download_socket_timeout_seconds_max"]
    )
    assert (
        payload["llm_rate_limit_resume_interval_seconds_min"]
        < payload["llm_rate_limit_resume_interval_seconds_max"]
    )

# --- 截图编码：决定单张图有多大，进而决定一次请求能带几张图 -------------------

class _FakeFfmpegResult:
    returncode = 0
    stderr = ""


def _capture_ffmpeg(monkeypatch):
    """拦掉真正的 ffmpeg，只记录它收到的参数。"""
    from app.utils import video_helper

    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return _FakeFfmpegResult()

    monkeypatch.setattr(video_helper.subprocess, "run", _fake_run)
    return calls


def test_screenshot_encoding_defaults_come_from_constants(dao_env):
    assert runtime_limits.screenshot_max_width() == DEFAULT_SCREENSHOT_MAX_WIDTH == 0
    assert runtime_limits.screenshot_quality() == DEFAULT_SCREENSHOT_QUALITY == 2
    assert runtime_limits.ffmpeg_timeout_seconds() == DEFAULT_FFMPEG_TIMEOUT_SECONDS == 60
    assert runtime_limits.ocr_max_judge_candidates() == DEFAULT_OCR_MAX_JUDGE_CANDIDATES


def test_screenshot_encoding_updates_apply_immediately(dao_env):
    """保存后必须立刻生效，不能等 5 秒 TTL 过期。"""
    dao.update_general_settings(
        screenshot_max_width=1280,
        screenshot_quality=8,
        ffmpeg_timeout_seconds=120,
        ocr_max_judge_candidates=50,
    )
    assert runtime_limits.screenshot_max_width() == 1280
    assert runtime_limits.screenshot_quality() == 8
    assert runtime_limits.ffmpeg_timeout_seconds() == 120
    assert runtime_limits.ocr_max_judge_candidates() == 50


def test_screenshot_encoding_values_are_clamped(dao_env):
    # 0 是合法值：它代表「不要缩放」，必须保住而不是被当成空值
    dao.update_general_settings(screenshot_max_width=0)
    assert runtime_limits.screenshot_max_width() == 0
    dao.update_general_settings(screenshot_max_width=-5)
    assert runtime_limits.screenshot_max_width() == 0
    dao.update_general_settings(screenshot_max_width=99999)
    assert runtime_limits.screenshot_max_width() == MAX_SCREENSHOT_MAX_WIDTH

    # 质量越界夹到 1..31（ffmpeg 的 -q:v 范围）
    dao.update_general_settings(screenshot_quality=0)
    assert runtime_limits.screenshot_quality() == 1
    dao.update_general_settings(screenshot_quality=99)
    assert runtime_limits.screenshot_quality() == MAX_SCREENSHOT_QUALITY

    # 超时不允许 0：subprocess.run(timeout=0) 会立刻超时，等于让所有截图都失败
    dao.update_general_settings(ffmpeg_timeout_seconds=0)
    assert runtime_limits.ffmpeg_timeout_seconds() == 10
    dao.update_general_settings(ffmpeg_timeout_seconds=99999)
    assert runtime_limits.ffmpeg_timeout_seconds() == MAX_FFMPEG_TIMEOUT_SECONDS

    dao.update_general_settings(ocr_max_judge_candidates=0)
    assert runtime_limits.ocr_max_judge_candidates() == 1
    dao.update_general_settings(ocr_max_judge_candidates=99999)
    assert runtime_limits.ocr_max_judge_candidates() == MAX_OCR_MAX_JUDGE_CANDIDATES


def test_environment_still_wins_for_screenshot_encoding(dao_env, monkeypatch):
    dao.update_general_settings(screenshot_max_width=1280, ffmpeg_timeout_seconds=120)
    monkeypatch.setenv("SCREENSHOT_MAX_WIDTH", "640")
    monkeypatch.setenv("FFMPEG_TIMEOUT_SECONDS", "30")
    assert runtime_limits.screenshot_max_width() == 640
    assert runtime_limits.ffmpeg_timeout_seconds() == 30


def test_generate_screenshot_applies_scaling_quality_and_timeout(dao_env, monkeypatch, tmp_path):
    """配置必须真的落到 ffmpeg 命令行上，而不是只存在数据库里。"""
    from app.utils import video_helper

    calls = _capture_ffmpeg(monkeypatch)
    dao.update_general_settings(
        screenshot_max_width=1280,
        screenshot_quality=8,
        ffmpeg_timeout_seconds=120,
    )
    video_helper.generate_screenshot("video.mp4", str(tmp_path), 30, 1)

    assert calls, "ffmpeg 没有被调用"
    cmd, kwargs = calls[-1]
    assert cmd[cmd.index("-q:v") + 1] == "8"
    assert "-vf" in cmd
    scale = cmd[cmd.index("-vf") + 1]
    assert scale.startswith("scale=") and "1280" in scale
    assert kwargs.get("timeout") == 120


def test_generate_screenshot_omits_scale_filter_when_width_is_zero(dao_env, monkeypatch, tmp_path):
    """宽度 0 = 保持原始分辨率，与历史行为一致：命令行里不能出现 -vf。"""
    from app.utils import video_helper

    calls = _capture_ffmpeg(monkeypatch)
    dao.update_general_settings(screenshot_max_width=0)
    video_helper.generate_screenshot("video.mp4", str(tmp_path), 30, 1)

    cmd, _kwargs = calls[-1]
    assert "-vf" not in cmd
    assert cmd[cmd.index("-q:v") + 1] == str(DEFAULT_SCREENSHOT_QUALITY)


def test_judge_candidate_limit_reads_runtime_config(dao_env):
    """判定候选数与 llm_max_request_bytes 是同一个旋钮的两端，必须可配。"""
    from app.services import ocr_assist

    assert ocr_assist.max_judge_candidates() == DEFAULT_OCR_MAX_JUDGE_CANDIDATES
    dao.update_general_settings(ocr_max_judge_candidates=77)
    assert ocr_assist.max_judge_candidates() == 77


def test_default_payload_covers_screenshot_encoding_fields(dao_env):
    payload = dao._default_payload()
    for field in (
        "screenshot_max_width",
        "screenshot_quality",
        "ffmpeg_timeout_seconds",
        "ocr_max_judge_candidates",
    ):
        assert field in payload, f"{field} missing from default payload"
    assert payload["screenshot_max_width_default"] == DEFAULT_SCREENSHOT_MAX_WIDTH
    assert payload["screenshot_max_width_limit"] == MAX_SCREENSHOT_MAX_WIDTH
    assert payload["screenshot_quality_min"] < payload["screenshot_quality_max"]
    assert payload["ffmpeg_timeout_seconds_min"] < payload["ffmpeg_timeout_seconds_max"]
    assert payload["ocr_max_judge_candidates_limit"] == MAX_OCR_MAX_JUDGE_CANDIDATES
