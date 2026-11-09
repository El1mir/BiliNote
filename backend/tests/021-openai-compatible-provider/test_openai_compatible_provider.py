from types import SimpleNamespace

import pytest

from app.gpt.provider.OpenAI_compatible_provider import _create_minimal_completion


class FakeCompletions:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.handler(kwargs)


def fake_client(handler):
    completions = FakeCompletions(handler)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def test_kouri_model_not_found_falls_back_to_max_tokens():
    def handler(kwargs):
        if "max_completion_tokens" in kwargs:
            raise RuntimeError("HTTP 503 model_not_found code=200105")
        return SimpleNamespace(choices=[])

    client, completions = fake_client(handler)

    result = _create_minimal_completion(client, "gpt-6-luna-codex")

    assert result.choices == []
    assert "max_completion_tokens" in completions.calls[0]
    assert "max_tokens" in completions.calls[1]


def test_legacy_provider_falls_back_when_parameter_is_rejected():
    def handler(kwargs):
        if "max_completion_tokens" in kwargs:
            raise RuntimeError("unknown parameter: max_completion_tokens")
        return SimpleNamespace(choices=[])

    client, completions = fake_client(handler)

    _create_minimal_completion(client, "legacy-model")

    assert "max_completion_tokens" in completions.calls[0]
    assert "max_tokens" in completions.calls[1]


def test_non_parameter_model_error_is_not_retried():
    error = RuntimeError("HTTP 401 invalid_api_key")

    def handler(kwargs):
        if "max_completion_tokens" in kwargs:
            raise error
        raise AssertionError("must not retry non parameter model error")

    client, completions = fake_client(handler)

    with pytest.raises(RuntimeError, match="invalid_api_key"):
        _create_minimal_completion(client, "broken-model")

    assert len(completions.calls) == 1
