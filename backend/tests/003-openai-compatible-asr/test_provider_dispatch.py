"""spec 003 ticket 03：openai-asr 在 transcriber_provider 的注册与实例缓存。"""
from app.transcriber import transcriber_provider as provider


class FakeOpenAIASR:
    def __init__(self, base_url, api_key, model, timeout=600, chunk_size_mb=18, name="",
                 api_style="transcriptions", max_speech_chunks=120, silence_noise_db=-30.0,
                 min_silence_seconds=0.5):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.chunk_size_mb = chunk_size_mb
        self.api_style = api_style
        self.max_speech_chunks = max_speech_chunks
        self.silence_noise_db = silence_noise_db
        self.min_silence_seconds = min_silence_seconds


def _reset(monkeypatch):
    monkeypatch.setattr(provider, "_transcribers", {key: None for key in provider._transcribers})
    monkeypatch.setattr(
        provider, "_transcriber_configs", {key: None for key in provider._transcribers}
    )
    monkeypatch.setattr(provider, "OpenAIASRTranscriber", FakeOpenAIASR)


def _options(model="m1"):
    return {"base_url": "https://api.x/v1", "api_key": "sk-1", "model": model}


def test_openai_asr_is_registered_as_transcriber_type():
    assert provider.TranscriberType("openai-asr") == provider.TranscriberType.OPENAI_ASR


def test_dispatch_and_cache_rebuild_on_config_change(monkeypatch):
    _reset(monkeypatch)

    a = provider.get_transcriber("openai-asr", transcriber_options=_options("m1"))
    assert isinstance(a, FakeOpenAIASR)
    assert a.model == "m1"

    # 相同配置 → 复用实例
    b = provider.get_transcriber("openai-asr", transcriber_options=_options("m1"))
    assert b is a

    # 换模型 → 按新配置重建
    c = provider.get_transcriber("openai-asr", transcriber_options=_options("m2"))
    assert c is not a
    assert c.model == "m2"


def test_dispatch_uses_endpoint_fields(monkeypatch):
    _reset(monkeypatch)
    options = {
        "base_url": "https://api.y/v1",
        "api_key": "sk-2",
        "model": "whisper-large-v3",
        "timeout": 120,
        "chunk_size_mb": 50,
        "name": "自建",
        "api_style": "chat",
    }
    transcriber = provider.get_transcriber("openai-asr", transcriber_options=options)
    assert transcriber.base_url == "https://api.y/v1"
    assert transcriber.api_key == "sk-2"
    assert transcriber.timeout == 120
    assert transcriber.chunk_size_mb == 50
    assert transcriber.api_style == "chat"
