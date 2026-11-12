"""spec 022 W1 验收 5：画面判定降级不触发任务级重试（D6）。

模型解析不出帧列表（WorthJudgementError）时，保留全部候选帧继续出笔记，
任务 detail 里写 judgement_degraded=true；网络/鉴权等真实 API 错误仍抛。
"""

import pytest

from app.services.note import NoteGenerator
from app.services.ocr_assist import WorthJudgementError


class _FakeGpt:
    def __init__(self, exc):
        self._exc = exc

    def judge_note_frames(self, *args, **kwargs):
        raise self._exc


def _generator(monkeypatch, statuses):
    generator = NoteGenerator()
    generator.video_img_urls = []

    def fake_update(task_id, status, **kwargs):
        statuses.append({"task_id": task_id, "status": status, **kwargs})

    monkeypatch.setattr(generator, "_update_status", fake_update)

    def fail_handle(*args, **kwargs):
        raise AssertionError("降级不该走 _handle_exception（那会触发整任务重试）")

    monkeypatch.setattr(generator, "_handle_exception", fail_handle)
    return generator


def test_empty_frames_degrades_and_keeps_candidates(monkeypatch):
    statuses = []
    generator = _generator(monkeypatch, statuses)
    monkeypatch.setattr(
        "app.services.runtime_limits.note_max_images", lambda: 3, raising=True
    )

    approved = generator._judge_note_frames(
        _FakeGpt(WorthJudgementError("判定结果里找不到帧列表")),
        transcript=None,
        task_id="w1-judge",
        candidates=[1.0, 2.5, 3.0],
    )

    assert [item.time for item in approved] == [1.0, 2.5, 3.0]
    assert generator.judgement_degraded
    degraded = [s for s in statuses if "judgement_degraded" in (s.get("detail") or {})]
    assert degraded and degraded[-1]["detail"]["judgement_degraded"] is True
    assert degraded[-1]["detail"]["judgement_degraded_reason"]


def test_degrade_respects_note_max_images(monkeypatch):
    statuses = []
    generator = _generator(monkeypatch, statuses)
    monkeypatch.setattr(
        "app.services.runtime_limits.note_max_images", lambda: 2, raising=True
    )

    approved = generator._judge_note_frames(
        _FakeGpt(WorthJudgementError("空帧列表")),
        transcript=None,
        task_id="w1-judge",
        candidates=[1.0, 2.0, 3.0, 4.0],
    )

    assert [item.time for item in approved] == [1.0, 2.0]


def test_real_api_error_still_raises(monkeypatch):
    statuses = []
    generator = _generator(monkeypatch, statuses)
    errors = []
    monkeypatch.setattr(generator, "_handle_exception", lambda t, e: errors.append(e))

    with pytest.raises(RuntimeError):
        generator._judge_note_frames(
            _FakeGpt(RuntimeError("401 unauthorized")),
            transcript=None,
            task_id="w1-judge",
            candidates=[1.0],
        )
    assert errors, "真实 API 错误必须走原失败路径"
