"""spec 022 W4：ASR 序列化不再打 Pydantic 告警 + id/seek 规整为 int。

对应验收第 7 条：上游把 segments[].id / seek 返回成字符串时，不再出现
"Expected int ... input_value='0'" 的 UserWarning，transcript 时间轴照常可用。
"""

from types import SimpleNamespace

from app.transcriber.openai_asr import (
    OpenAIASRTranscriber,
    _normalize_raw_payload,
)

_to_dict = OpenAIASRTranscriber._to_dict


class _Seg:
    def __init__(self, text, start, end):
        self.text = text
        self.start = start
        self.end = end


class _Transcription:
    def __init__(self):
        self.text = "hello world"
        self.language = "en"
        self.segments = [_Seg("hello", 0.0, 1.0), _Seg("world", 1.0, 2.0)]
        self.dump_kwargs = None

    def model_dump(self, **kwargs):
        self.dump_kwargs = kwargs
        return {
            "text": "hello world",
            "language": "en",
            "segments": [
                {"id": "0", "seek": "12", "text": "hello", "start": 0.0, "end": 1.0},
                {"id": 2, "seek": "1500", "text": "world", "start": 1.0, "end": 2.0},
            ],
        }


def test_model_dump_is_called_with_warnings_disabled():
    obj = _Transcription()
    raw = _to_dict(obj)
    assert obj.dump_kwargs == {"warnings": False}, (
        f"必须传 warnings=False，实际 {obj.dump_kwargs}"
    )
    assert raw["segments"][0]["id"] == "0", "序列化层不该偷偷改字段，规整在 normalize 里做"


def test_model_dump_without_warnings_argument_still_works():
    class _OldPydantic:
        def model_dump(self):
            return {"text": "ok"}

    assert _to_dict(_OldPydantic()) == {"text": "ok"}, "老版 Pydantic 不认识 warnings 时要回退"


def test_normalize_coerces_string_ids_and_keeps_other_fields():
    raw = {
        "text": "x",
        "segments": [
            {"id": "0", "seek": "12", "text": "a", "start": 0.0},
            {"id": "oops", "seek": "1.5", "text": "b"},
            {"id": True, "text": "c"},
        ],
    }
    normalized = _normalize_raw_payload(raw)

    assert normalized["segments"][0]["id"] == 0
    assert normalized["segments"][0]["seek"] == 12
    assert normalized["segments"][0]["text"] == "a", "其它字段必须原样保留"
    assert normalized["segments"][1]["id"] == "oops", "认不出来的值不猜，保持原样"
    assert normalized["segments"][1]["seek"] == "1.5", "非整数值不规整，保持原样"
    assert normalized["segments"][2]["id"] is True
    # 不改写上游对象：`raw` 仍可作原始证据
    assert raw["segments"][0]["id"] == "0"


def test_to_result_exposes_int_ids_and_keeps_timeline():
    obj = _Transcription()
    transcriber = object.__new__(OpenAIASRTranscriber)
    transcriber.api_style = "json"

    result = transcriber._to_result(obj, "unused.wav")

    assert [seg.text for seg in result.segments] == ["hello", "world"]
    assert result.raw["segments"][0]["id"] == 0
    assert result.raw["segments"][1]["seek"] == 1500
    assert result.raw["segments"][1]["id"] == 2
    assert result.full_text == "hello world"
