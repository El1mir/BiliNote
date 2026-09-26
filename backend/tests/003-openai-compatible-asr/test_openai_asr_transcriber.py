"""spec 003 ticket 02/09：OpenAIASRTranscriber 的请求 / 降级 / 切割合并行为。"""
from types import SimpleNamespace
from unittest import mock

import pytest

from app.transcriber import openai_asr
from app.transcriber.openai_asr import OpenAIASRTranscriber


class FakeTranscriptions:
    def __init__(self, handler):
        self.handler = handler

    def create(self, **kwargs):
        return self.handler(kwargs)


def _client(handler):
    return SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions(handler)))


def test_verbose_json_parses_segments(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")

    def handler(kwargs):
        assert kwargs["response_format"] == "verbose_json"
        assert kwargs["model"] == "whisper-1"
        return SimpleNamespace(
            text="你好 世界",
            language="zh",
            segments=[
                SimpleNamespace(start=0.0, end=1.0, text="你好"),
                SimpleNamespace(start=1.0, end=2.0, text="世界"),
            ],
        )

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)):
        result = OpenAIASRTranscriber("https://api.x/v1", "sk-xxx", "whisper-1").transcript(str(f))

    assert result.full_text == "你好 世界"
    assert result.language == "zh"
    assert [s.text for s in result.segments] == ["你好", "世界"]


def test_falls_back_to_json_when_verbose_unsupported(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    calls = []

    def handler(kwargs):
        calls.append(kwargs["response_format"])
        if kwargs["response_format"] == "verbose_json":
            raise RuntimeError("response_format=verbose_json is not supported")
        return SimpleNamespace(text="hello world")

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)), \
            mock.patch.object(openai_asr, "probe_duration_seconds", return_value=12.0):
        result = OpenAIASRTranscriber("https://api.x/v1", "sk-xxx", "m").transcript(str(f))

    assert calls == ["verbose_json", "json"]
    assert result.full_text == "hello world"
    # 没有分段时造一个覆盖全片的单段
    assert len(result.segments) == 1
    assert result.segments[0].end == 12.0


def test_falls_back_to_text(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    calls = []

    def handler(kwargs):
        calls.append(kwargs["response_format"])
        if kwargs["response_format"] in ("verbose_json", "json"):
            raise RuntimeError("response_format is not supported")
        return "plain text"

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)), \
            mock.patch.object(openai_asr, "probe_duration_seconds", return_value=0.0):
        result = OpenAIASRTranscriber("https://api.x/v1", "sk-xxx", "m").transcript(str(f))

    assert calls == ["verbose_json", "json", "text"]
    assert result.full_text == "plain text"
    assert result.segments[0].text == "plain text"


def test_non_format_error_is_not_swallowed(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")

    def handler(kwargs):
        raise RuntimeError("401 Unauthorized")

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)):
        with pytest.raises(RuntimeError, match="401"):
            OpenAIASRTranscriber("https://api.x/v1", "sk-xxx", "m").transcript(str(f))


def test_splits_when_over_threshold_and_merges_with_offset(tmp_path):
    f = tmp_path / "big.mp3"
    # 阈值下限是 256KB，文件要真的超过才会切
    f.write_bytes(b"x" * 300_000)
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    c1 = chunk_dir / "chunk_000.mp3"
    c1.write_bytes(b"a")
    c2 = chunk_dir / "chunk_001.mp3"
    c2.write_bytes(b"b")
    calls = []

    def handler(kwargs):
        calls.append(kwargs["file"][0])
        return SimpleNamespace(
            text="seg-text",
            language="zh",
            segments=[SimpleNamespace(start=0.0, end=1.0, text="seg-text")],
        )

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)),             mock.patch.object(
                openai_asr, "split_audio", return_value=([str(c1), str(c2)], str(chunk_dir))
            ) as sp,             mock.patch.object(openai_asr, "probe_duration_seconds", side_effect=[60.0, 60.0, 60.0]):
        result = OpenAIASRTranscriber(
            "https://api.x/v1", "sk-xxx", "m", chunk_size_mb=0.00001
        ).transcript(str(f))

    sp.assert_called_once()
    # 两段分别请求
    assert len(calls) == 2
    # 第二段的分段要按前一段时长整体偏移
    assert [round(x.start) for x in result.segments] == [0, 60]
    assert [round(x.end) for x in result.segments] == [1, 61]
    assert result.full_text == "seg-text seg-text"
    assert result.language == "zh"
    # 切割出来的临时目录用完要删掉
    assert not chunk_dir.exists()


def test_too_many_chunks_raises(tmp_path):
    f = tmp_path / "huge.mp3"
    f.write_bytes(b"x" * 100)
    transcriber = OpenAIASRTranscriber("https://api.x/v1", "sk", "m")
    with mock.patch.object(openai_asr, "probe_duration_seconds", return_value=3600.0):
        with pytest.raises(ValueError, match="超过上限"):
            transcriber._transcribe_in_chunks(None, str(f), size=10 ** 9, limit=1)


def test_missing_model_raises():
    with pytest.raises(ValueError):
        OpenAIASRTranscriber("https://api.x/v1", "sk", "")


class FakeAPIError(Exception):
    """模拟 openai SDK 的 APIStatusError：带 status_code 和原始 response。"""

    def __init__(self, message, status_code=None, text=""):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(text=text) if text else None


def _raises_with(handler, exc):
    f = None
    import tempfile
    import pathlib as _pathlib

    with tempfile.TemporaryDirectory() as tmp:
        f = _pathlib.Path(tmp) / "a.mp3"
        f.write_bytes(b"x")
        with mock.patch.object(openai_asr, "build_openai_client", return_value=_client(handler)):
            try:
                OpenAIASRTranscriber("https://token-plan-cn.xiaomimimo.com/v1", "sk", "m").transcript(str(f))
            except Exception as e:  # noqa: BLE001
                exc.append(e)


def test_friendly_error_for_404_html():
    html = "<html><head><title>404 Not Found</title></head><body><center><h1>404 Not Found</h1></center><hr><center>openresty</center></body></html>"

    def handler(kwargs):
        raise FakeAPIError("Error code: 404 - " + html, status_code=404, text=html)

    errs = []
    _raises_with(handler, errs)
    assert errs, "应抛出异常"
    message = str(errs[0])
    assert "404" in message
    assert "Base URL" in message
    # 不能再把整页 HTML 糊出来
    assert "<html" not in message
    assert "openresty" not in message


def test_friendly_error_for_401():
    def handler(kwargs):
        raise FakeAPIError("Error code: 401 - Unauthorized", status_code=401)

    errs = []
    _raises_with(handler, errs)
    assert "鉴权失败" in str(errs[0])


def test_friendly_error_for_timeout():
    def handler(kwargs):
        raise FakeAPIError("Request timed out after 60s", status_code=None)

    errs = []
    _raises_with(handler, errs)
    assert "超时" in str(errs[0])


class FakeChatCompletions:
    def __init__(self, handler):
        self.handler = handler

    def create(self, **kwargs):
        return self.handler(kwargs)


def _chat_client(handler):
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions(handler)))


def test_chat_style_sends_input_audio_and_parses_text(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"audio-bytes")
    seen = {}

    def handler(kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="你好，世界"))]
        )

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_chat_client(handler)), \
            mock.patch.object(openai_asr, "probe_duration_seconds", return_value=3.0):
        result = OpenAIASRTranscriber(
            "https://token-plan-cn.xiaomimimo.com/v1",
            "sk",
            "mimo-v2.5-asr",
            api_style="chat",
        ).transcript(str(f))

    assert seen["model"] == "mimo-v2.5-asr"
    part = seen["messages"][0]["content"][0]
    assert part["type"] == "input_audio"
    assert part["input_audio"]["data"].startswith("data:audio/mpeg;base64,")
    assert result.full_text == "你好，世界"
    # chat 风格没有分段，造一个覆盖全片的单段
    assert len(result.segments) == 1
    assert result.segments[0].end == 3.0


def test_chat_style_uses_wav_mime_for_wav(tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"audio-bytes")
    seen = {}

    def handler(kwargs):
        seen.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))])

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_chat_client(handler)), \
            mock.patch.object(openai_asr, "probe_duration_seconds", return_value=0.0):
        OpenAIASRTranscriber("https://x/v1", "sk", "m", api_style="chat").transcript(str(f))

    assert seen["messages"][0]["content"][0]["input_audio"]["data"].startswith("data:audio/wav;base64,")


def test_chat_style_splits_at_base64_cap(tmp_path):
    # 8MB > chat 的 7.5MB base64 上限，即使 chunk_size_mb 设 18 也应该切割
    f = tmp_path / "big.mp3"
    f.write_bytes(b"x" * (8 * 1024 * 1024))
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    c1 = chunk_dir / "chunk_000.mp3"
    c1.write_bytes(b"a")
    c2 = chunk_dir / "chunk_001.mp3"
    c2.write_bytes(b"b")
    seen = []

    def handler(kwargs):
        seen.append(kwargs["messages"][0]["content"][0]["input_audio"]["data"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))]
        )

    with mock.patch.object(openai_asr, "build_openai_client", return_value=_chat_client(handler)),             mock.patch.object(
                openai_asr, "split_audio", return_value=([str(c1), str(c2)], str(chunk_dir))
            ) as sp,             mock.patch.object(openai_asr, "probe_duration_seconds", return_value=10.0):
        result = OpenAIASRTranscriber(
            "https://x/v1", "sk", "m", api_style="chat", chunk_size_mb=18
        ).transcript(str(f))

    sp.assert_called_once()
    assert len(seen) == 2
    assert result.full_text == "hi hi"
    assert not chunk_dir.exists()


def test_unknown_api_style_falls_back_to_transcriptions():
    transcriber = OpenAIASRTranscriber("https://x/v1", "sk", "m", api_style="bogus")
    assert transcriber.api_style == "transcriptions"
