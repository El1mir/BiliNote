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


def test_rate_limit_error_is_marked_non_retryable(monkeypatch):
    transcriber = openai_asr.OpenAIASRTranscriber(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="test-model",
    )

    class FakeRateLimitError(Exception):
        status_code = 429

    def fake_transcribe_one(client, path):
        raise FakeRateLimitError("Too many requests")

    monkeypatch.setattr(transcriber, "_transcribe_one", fake_transcribe_one)

    with pytest.raises(RuntimeError) as exc_info:
        transcriber._safe_transcribe(client=None, path="demo.mp3")

    assert getattr(exc_info.value, "non_retryable", False) is True
