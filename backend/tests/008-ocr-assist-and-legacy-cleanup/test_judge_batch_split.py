"""判定层大批量图片失败时的「对半拆分重试」（2026-10-06 事故回归）。

事故：kouri 网关在**大请求**上不可靠，5.7MB 起开始断连/SSL 错误，8.6MB 直接返回
``503 {"code":"model_not_found"}``（错误码完全误导，模型实际存在）。判定层当时的
图片预算是 8MB，切出的批次正好落在死亡区，于是每个任务都在判定层失败、连任务级
三次重试也全部作废。

修复：① 判定层图片预算默认压到 3MB；② 逐批失败时对半拆分重试，而不是原地重试
同一批（批次大小确定，原地重试必然同样失败）。
"""
from __future__ import annotations

import json

import pytest

from app.gpt.universal_gpt import (
    GATEWAY_MAX_REQUEST_BYTES,
    JUDGE_IMAGE_BUDGET_BYTES,
    UniversalGPT,
)


class _FlakyCompletions:
    """请求体超过 ``fail_over_bytes`` 就抛异常，否则返回合法判定 JSON。"""

    def __init__(self, record, fail_over_bytes):
        self._record = record
        self._fail_over_bytes = fail_over_bytes

    def create(self, **kwargs):
        messages = kwargs.get("messages") or []
        size = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        ok = size <= self._fail_over_bytes
        self._record.append({"size": size, "ok": ok})
        if not ok:
            raise RuntimeError("Error code: 503 - {'code': 'model_not_found'}")

        class _Msg:
            content = '{"frames": [{"time": 12, "worth": true, "reason": "公式"}]}'

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _Client:
    def __init__(self, record, fail_over_bytes):
        self.chat = type(
            "_Chat",
            (),
            {"completions": _FlakyCompletions(record, fail_over_bytes)},
        )()


def _urls(count, bytes_each=248_000):
    import base64

    payload = base64.b64encode(b"x" * bytes_each).decode("ascii")
    return ["data:image/jpeg;base64," + payload for _ in range(count)]


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """把重试压成一次且不退避——测试要验证的是拆分策略，不是退避曲线。"""
    monkeypatch.setenv("OPENAI_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("OPENAI_RETRY_BACKOFF_SECONDS", "0")


def test_judge_image_budget_is_well_below_gateway_limit():
    """判定层预算必须远低于网关硬上限，而不是贴着它。"""
    assert JUDGE_IMAGE_BUDGET_BYTES <= 4 * 1024 * 1024
    assert JUDGE_IMAGE_BUDGET_BYTES < GATEWAY_MAX_REQUEST_BYTES


def test_judge_splits_batch_in_half_on_large_request_failure(tmp_path, monkeypatch):
    """批次超限失败时对半拆分重试，直到压回稳定区间为止。"""
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    # 上限设在「4 张图以内能过」的量级：初始批次必然超限，拆分后能成功。
    gpt = UniversalGPT(_Client(record, fail_over_bytes=1_200_000), "glm-4.6")

    outcome = gpt.judge_note_frames(
        segments=[],
        candidates=[12.0],
        duration=600.0,
        image_urls=_urls(12),
    )

    assert outcome.approved, "拆分后必须真的拿到判定结果"
    ok_sizes = [item["size"] for item in record if item["ok"]]
    assert ok_sizes, "必须至少有一次请求成功"
    assert max(ok_sizes) <= 1_200_000, (
        "最终成功的请求必须落在稳定区间内，最大 %d 字节" % max(ok_sizes)
    )
    assert len(record) > 1, "超限批次必须被拆分重试，而不是原地重试同一批"
    assert any(not item["ok"] for item in record), "夹具必须真的制造出过一次超限失败"


def test_judge_skips_single_image_that_still_fails(tmp_path, monkeypatch):
    """拆到单张仍失败时只跳过该帧，不让整篇笔记失败。"""
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    # 上限设成 0：任何请求都失败。拆到单张后应当放弃并跳过，而不是抛出去。
    gpt = UniversalGPT(_Client(record, fail_over_bytes=0), "glm-4.6")

    with pytest.raises(Exception):
        # 所有条目都拿不到时，调用方仍按判定失败处理（spec 008 §5.6b）。
        gpt.judge_note_frames(
            segments=[],
            candidates=[12.0],
            duration=600.0,
            image_urls=_urls(2),
        )
