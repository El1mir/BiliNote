import pytest

from app.transcriber import openai_asr


def test_rate_limiter_spaces_calls_to_target_qps(monkeypatch):
    clock = {"now": 0.0}
    sleeps = []

    def fake_monotonic():
        return clock["now"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(openai_asr.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(openai_asr.time, "sleep", fake_sleep)

    limiter = openai_asr._RateLimiter(max_per_minute=30)
    limiter.wait()  # first request goes immediately
    limiter.wait()  # second request must wait 2s at 30 RPM

    assert sleeps == pytest.approx([2.0])


def _transcriber_raising(monkeypatch, error):
    transcriber = openai_asr.OpenAIASRTranscriber(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="test-model",
    )

    def fake_transcribe_one(client, path):
        raise error

    monkeypatch.setattr(transcriber, "_transcribe_one", fake_transcribe_one)
    return transcriber


def test_rate_limit_error_is_marked_rate_limited_not_non_retryable(monkeypatch):
    """429 是「还没轮到」，不是「不可重试」（spec 012）。

    早期实现把 429 也标成 ``non_retryable`` —— 那时「不可重试」是唯一能表达
    「别重跑整条流水线（重复下载 + 切片）」的手段。spec 012 起 429 改走等待路径：
    由 ``_execute_note_with_retry`` 等全局冷却窗口后重试，等满上限就交还队列。
    所以这里必须**只**打 ``rate_limited``，否则任务会被直接判失败。
    """

    class FakeRateLimitError(Exception):
        status_code = 429

    transcriber = _transcriber_raising(
        monkeypatch, FakeRateLimitError("Too many requests")
    )

    with pytest.raises(RuntimeError) as exc_info:
        transcriber._safe_transcribe(client=None, path="demo.mp3")

    assert getattr(exc_info.value, "rate_limited", False) is True
    assert getattr(exc_info.value, "non_retryable", False) is False


def test_auth_error_is_still_non_retryable(monkeypatch):
    """鉴权失败重跑整条流程只会重复下载和切片，仍然标不可重试。"""

    class FakeAuthError(Exception):
        status_code = 401

    transcriber = _transcriber_raising(monkeypatch, FakeAuthError("Invalid API key"))

    with pytest.raises(RuntimeError) as exc_info:
        transcriber._safe_transcribe(client=None, path="demo.mp3")

    assert getattr(exc_info.value, "non_retryable", False) is True
    assert getattr(exc_info.value, "rate_limited", False) is False
