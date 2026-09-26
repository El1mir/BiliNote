"""spec 003 ticket 04：OpenAI 兼容 ASR 路由（直接调用函数，避免启动整个 app）。"""
import json
from unittest import mock

import pytest

from app.routers import config as config_router
from app.services.transcriber_config_manager import TranscriberConfigManager


def _body(response):
    return json.loads(response.body)


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    mgr = TranscriberConfigManager(str(tmp_path / "transcriber.json"))
    monkeypatch.setattr(config_router, "transcriber_config_manager", mgr)
    return mgr


def _request(**overrides):
    data = {
        "name": "测试端点",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-1234567890abcdef",
        "model": "whisper-1",
    }
    data.update(overrides)
    return config_router.OpenAISREndpointRequest(**data)


def test_crud_and_masked_public_config(manager):
    body = _body(config_router.add_openai_asr(_request()))
    assert body["code"] == 0
    endpoint_id = body["data"]["id"]

    # public config 不回传明文 key
    public = _body(config_router.get_transcriber_config())["data"]
    assert public["openai_asr_id"] == endpoint_id
    assert public["openai_asr_endpoints"][0]["api_key"] != "sk-1234567890abcdef"

    # 更新（api_key 传打码值 → 不覆盖）
    body = _body(
        config_router.update_openai_asr(
            endpoint_id, _request(api_key="sk-1****cdef", model="whisper-large-v3")
        )
    )
    assert body["code"] == 0
    assert manager.get_openai_asr(endpoint_id)["api_key"] == "sk-1234567890abcdef"
    assert manager.get_openai_asr(endpoint_id)["model"] == "whisper-large-v3"

    # 删除
    body = _body(config_router.delete_openai_asr(endpoint_id))
    assert body["code"] == 0
    assert manager.list_openai_asr() == []


def test_add_rejects_empty_model(manager):
    body = _body(config_router.add_openai_asr(_request(model="")))
    assert body["code"] != 0
    assert "模型名" in body["msg"]


def test_save_transcriber_config_selects_endpoint(manager):
    endpoint_id = manager.add_openai_asr("a", "https://x/v1", "k-1234567890", "m")
    body = _body(
        config_router.update_transcriber_config(
            config_router.TranscriberConfigRequest(
                transcriber_type="openai-asr", openai_asr_id=endpoint_id
            )
        )
    )
    assert body["code"] == 0
    assert body["data"]["transcriber_type"] == "openai-asr"
    assert body["data"]["openai_asr_id"] == endpoint_id


def test_test_endpoint_returns_readable_failure(manager):
    endpoint_id = manager.add_openai_asr(
        "a", "https://x/v1", "sk-1234567890abcdef", "m"
    )
    with mock.patch(
        "app.transcriber.openai_asr.build_openai_client",
        side_effect=RuntimeError("401 Unauthorized"),
    ):
        body = _body(config_router.test_openai_asr(endpoint_id))

    assert body["code"] != 0
    assert "401" in body["msg"]
    assert body["data"]["ok"] is False


def test_test_endpoint_success(manager):
    endpoint_id = manager.add_openai_asr(
        "a", "https://x/v1", "sk-1234567890abcdef", "m"
    )
    fake_client = mock.MagicMock()
    fake_client.audio.transcriptions.create.return_value = mock.Mock(
        text="", language=None, segments=[]
    )
    with mock.patch(
        "app.transcriber.openai_asr.build_openai_client", return_value=fake_client
    ):
        body = _body(config_router.test_openai_asr(endpoint_id))

    assert body["code"] == 0
    assert body["data"]["ok"] is True


def test_test_endpoint_missing(manager):
    body = _body(config_router.test_openai_asr("nope"))
    assert body["code"] != 0


def test_api_style_is_passed_through(manager):
    body = _body(config_router.add_openai_asr(_request(api_style="chat")))
    assert body["code"] == 0
    endpoint_id = body["data"]["id"]
    assert manager.get_openai_asr(endpoint_id)["api_style"] == "chat"

    body = _body(config_router.add_openai_asr(_request(api_style="bogus")))
    assert body["code"] != 0
    assert "接口类型" in body["msg"]
