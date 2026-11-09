from unittest.mock import Mock

import pytest

from app.gpt.provider.OpenAI_compatible_provider import _create_minimal_completion


def test_prefers_max_completion_tokens():
    client = Mock()
    _create_minimal_completion(client, "gpt-6-luna-codex")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 1
    assert "max_tokens" not in kwargs


def test_falls_back_to_max_tokens_for_legacy_provider():
    client = Mock()
    client.chat.completions.create.side_effect = [
        ValueError("max_completion_tokens is unsupported"),
        object(),
    ]
    result = _create_minimal_completion(client, "legacy-model")
    assert result is not None
    calls = client.chat.completions.create.call_args_list
    assert calls[0].kwargs["max_completion_tokens"] == 1
    assert calls[1].kwargs["max_tokens"] == 1


def test_does_not_retry_non_parameter_errors():
    client = Mock()
    client.chat.completions.create.side_effect = RuntimeError("model_not_found")
    with pytest.raises(RuntimeError, match="model_not_found"):
        _create_minimal_completion(client, "missing-model")
    assert client.chat.completions.create.call_count == 1
