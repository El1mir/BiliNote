"""spec 006 ticket 01：ASR 切片转写并发（chunk_concurrency）。

并发只用来填满 max_rpm 允许的请求预算；真正的节流仍由线程安全的 _RateLimiter
负责。因此这里验证三件事：
  1. chunk_concurrency 的默认值 / 范围收敛 / 环境变量兜底；
  2. 并发结果与入参顺序一致（字幕顺序不能乱）；
  3. 并发数 > 1 时确实在同时发请求；= 1 时退化为原来的串行行为。
"""
import threading
import time

from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.transcriber import openai_asr


def _transcriber(**kwargs):
    kwargs.setdefault("base_url", "https://example.invalid/v1")
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("model", "test-model")
    return openai_asr.OpenAIASRTranscriber(**kwargs)


def test_default_and_range(monkeypatch):
    monkeypatch.delenv("OPENAI_ASR_CHUNK_CONCURRENCY", raising=False)

    assert _transcriber().chunk_concurrency == openai_asr._DEFAULT_CHUNK_CONCURRENCY
    assert _transcriber(chunk_concurrency=1).chunk_concurrency == 1
    assert _transcriber(chunk_concurrency=0).chunk_concurrency == 1
    assert _transcriber(chunk_concurrency=900).chunk_concurrency == openai_asr._CHUNK_CONCURRENCY_MAX


def test_env_fallback_and_bad_value(monkeypatch):
    monkeypatch.setenv("OPENAI_ASR_CHUNK_CONCURRENCY", "7")
    assert _transcriber().chunk_concurrency == 7

    monkeypatch.setenv("OPENAI_ASR_CHUNK_CONCURRENCY", "not-a-number")
    assert _transcriber().chunk_concurrency == openai_asr._DEFAULT_CHUNK_CONCURRENCY


def test_map_concurrently_preserves_input_order(monkeypatch):
    transcriber = _transcriber(chunk_concurrency=4)
    reports = []
    monkeypatch.setattr(
        transcriber,
        "_report_progress",
        lambda current, total, message="": reports.append((current, total)),
    )

    def worker(item):
        # 后面的先完成：结果仍必须按入参顺序收集
        time.sleep(0.01 * (7 - item))
        return item * 10

    assert transcriber._map_concurrently(worker, [1, 2, 3, 4, 5, 6]) == [10, 20, 30, 40, 50, 60]
    assert reports and reports[-1] == (6, 6)


def test_map_concurrently_is_serial_when_one():
    transcriber = _transcriber(chunk_concurrency=1)
    order = []

    def worker(item):
        order.append(item)
        return item

    assert transcriber._map_concurrently(worker, [1, 2, 3]) == [1, 2, 3]
    assert order == [1, 2, 3]


def test_map_concurrently_actually_parallel():
    transcriber = _transcriber(chunk_concurrency=4)
    lock = threading.Lock()
    state = {"running": 0, "peak": 0}

    def worker(item):
        with lock:
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
        time.sleep(0.05)
        with lock:
            state["running"] -= 1
        return item

    assert transcriber._map_concurrently(worker, list(range(8))) == list(range(8))
    assert state["peak"] >= 2, "并发数 > 1 时应该同时有多个请求在飞"


def _patch_speech_pipeline(monkeypatch, transcriber, tmp_path, cut_count=4):
    cuts = [
        (float(i), float(i + 1), str(tmp_path / f"cut{i}.mp3"))
        for i in range(cut_count)
    ]
    regions = [(float(i), float(i + 1)) for i in range(cut_count)]
    monkeypatch.setattr(openai_asr, "detect_speech_regions", lambda *a, **k: regions)
    monkeypatch.setattr(openai_asr, "merge_regions_to_limit", lambda r, **k: r)
    monkeypatch.setattr(transcriber, "_split_regions_by_limit", lambda r, p, limit: r)
    monkeypatch.setattr(
        openai_asr,
        "cut_audio_regions",
        lambda path, regs: (cuts, str(tmp_path / "cuts")),
    )
    return cuts


def test_speech_transcription_keeps_cut_order(monkeypatch, tmp_path):
    transcriber = _transcriber(chunk_concurrency=4)
    cuts = _patch_speech_pipeline(monkeypatch, transcriber, tmp_path, cut_count=4)

    lock = threading.Lock()
    seen = []

    def fake_safe(client, path):
        with lock:
            seen.append(path)
        # chat 风格只回一段文字：真实起止时间由切片边界补回
        return TranscriptResult(
            language="zh",
            full_text=path,
            segments=[TranscriptSegment(start=0.0, end=1.0, text=path)],
            raw={},
        )

    monkeypatch.setattr(transcriber, "_safe_transcribe", fake_safe)

    result = transcriber._transcribe_by_speech(
        client=None, file_path=str(tmp_path / "audio.mp3"), limit=1024
    )

    assert result is not None
    assert sorted(seen) == sorted(cut[2] for cut in cuts)
    assert [seg.start for seg in result.segments] == [cut[0] for cut in cuts]
