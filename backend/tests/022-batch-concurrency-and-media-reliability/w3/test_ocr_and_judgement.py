"""spec 022 W3：OCR 429 重试 + 进程级全局名额 + 帧判定降级。

对应验收第 5/6 条：

* 429 → 200 能重试成功；持续 429 三次后抛出，任务不因单张图失败（由上层计数）。
* 12 路并发受 OCR_MAX_CONCURRENCY（默认 4）约束。
* 判定返回显式空清单记 degraded=empty_frames；全批次解析失败记 parse_failed，
  都保留全部候选、不抛到任务级。
"""

import threading
import time
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.gpt.universal_gpt import UniversalGPT
from app.services import ocr_client
from app.services.ocr_assist import (
    WorthJudgementError,
    parse_worth_judgement,
)
from app.services.ocr_client import OcrClient, OcrError


def _client() -> OcrClient:
    client = object.__new__(OcrClient)
    client._config = {"model_name": "test-model"}
    return client


def test_429_then_success_retries_once(monkeypatch, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"x")
    calls = []

    def fake_once(path):
        calls.append(path)
        if len(calls) == 1:
            raise OcrError("rate limited", status_code=429)
        return SimpleNamespace(markdown="ok")

    monkeypatch.setattr(ocr_client.time, "sleep", lambda *_: None)
    client = _client()
    monkeypatch.setattr(client, "_recognize_once", fake_once)

    result = client.recognize_image(image)

    assert result.markdown == "ok"
    assert len(calls) == 2, f"429 后应重试一次，实际调用 {len(calls)} 次"


def test_non_retryable_error_is_not_retried(monkeypatch, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"x")
    calls = []

    def fake_once(path):
        calls.append(path)
        raise OcrError("bad key", status_code=401)

    monkeypatch.setattr(ocr_client.time, "sleep", lambda *_: None)
    client = _client()
    monkeypatch.setattr(client, "_recognize_once", fake_once)

    with pytest.raises(OcrError):
        client.recognize_image(image)
    assert len(calls) == 1, "401 属不可重试，必须只调用一次"


def test_persistent_429_gives_up_after_three_attempts(monkeypatch, tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"x")
    calls = []
    sleeps = []

    def fake_once(path):
        calls.append(path)
        raise OcrError("rate limited", status_code=429)

    monkeypatch.setattr(ocr_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = _client()
    monkeypatch.setattr(client, "_recognize_once", fake_once)

    with pytest.raises(OcrError):
        client.recognize_image(image)

    assert len(calls) == ocr_client.OCR_MAX_ATTEMPTS == 3
    assert len(sleeps) == 2, f"三次尝试之间应等两次，实际 {len(sleeps)}"
    assert all(0 < s <= ocr_client.OCR_RETRY_MAX_SLEEP_SECONDS for s in sleeps)


def test_ocr_max_concurrency_env_override(monkeypatch):
    monkeypatch.delenv("OCR_MAX_CONCURRENCY", raising=False)
    assert ocr_client.ocr_max_concurrency() == ocr_client.OCR_MAX_CONCURRENCY_DEFAULT == 4
    monkeypatch.setenv("OCR_MAX_CONCURRENCY", "2")
    assert ocr_client.ocr_max_concurrency() == 2
    monkeypatch.setenv("OCR_MAX_CONCURRENCY", "nonsense")
    assert ocr_client.ocr_max_concurrency() == 4


def test_global_semaphore_caps_twelve_concurrent_calls(monkeypatch):
    """12 路并发同时抢名额，任一时刻最多 4 个在跑。"""
    monkeypatch.setenv("OCR_MAX_CONCURRENCY", "4")
    monkeypatch.setattr(ocr_client, "_OCR_SEMAPHORE", None)
    monkeypatch.setattr(ocr_client, "_OCR_SEMAPHORE_SIZE", 0)

    gate = ocr_client._ocr_semaphore()
    state = {"current": 0, "max_seen": 0}
    lock = threading.Lock()

    def worker():
        with gate:
            with lock:
                state["current"] += 1
                state["max_seen"] = max(state["max_seen"], state["current"])
            time.sleep(0.02)
            with lock:
                state["current"] -= 1

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert state["max_seen"] == 4, f"全局名额应钳到 4，实际峰值 {state['max_seen']}"


def test_explicit_empty_frames_degrades_to_all_candidates():
    outcome = parse_worth_judgement('{"frames": []}', [1, 2, 3], max_images=2)
    assert outcome.degraded == "empty_frames"
    assert len(outcome.approved) == 2, "降级后应保留候选并受上限截断"
    assert outcome.dropped_by_cap == 1
    assert [d.time for d in outcome.approved] == [1.0, 2.0]


class _JudgeStub:
    """只装配 judge_note_frames 需要的三个依赖。"""

    ensure_segments_type = UniversalGPT.ensure_segments_type
    _build_plan_lines = UniversalGPT._build_plan_lines

    def __init__(self, content):
        self._content = content

    def _chat_completion_create(self, messages):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))]
        )


def test_garbage_judgement_degrades_without_raising():
    stub = _JudgeStub("这不是 JSON")
    outcome = UniversalGPT.judge_note_frames(
        stub, segments=[], candidates=[1, 2, 3], max_items=3
    )
    assert outcome.degraded == "parse_failed"
    assert len(outcome.approved) == 3, "解析失败必须保留全部候选，而不是抛到任务级"


def test_parse_failure_still_raises_at_parse_layer():
    """解析层仍保留异常，方便其它调用方识别「完全不可解析」。"""
    with pytest.raises(WorthJudgementError):
        parse_worth_judgement("not json", [1, 2, 3])
