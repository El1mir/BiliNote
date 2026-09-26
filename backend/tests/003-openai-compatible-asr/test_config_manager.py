"""spec 003 ticket 01/03：OpenAI 兼容 ASR 配置管理 + 就绪门禁。"""
import pytest

from app.services.transcriber_config_manager import TranscriberConfigManager


@pytest.fixture()
def manager(tmp_path):
    return TranscriberConfigManager(str(tmp_path / "transcriber.json"))


def test_add_list_update_delete(manager):
    eid = manager.add_openai_asr(
        "测试", "https://api.example.com/v1", "sk-1234567890abcdef", "whisper-1"
    )
    endpoints = manager.list_openai_asr()
    assert len(endpoints) == 1
    assert endpoints[0]["id"] == eid
    assert endpoints[0]["timeout"] == 600
    assert endpoints[0]["chunk_size_mb"] == 18
    # 第一条自动成为当前使用
    assert manager.get_config()["openai_asr_id"] == eid
    assert manager.get_active_openai_asr()["model"] == "whisper-1"

    manager.update_openai_asr(eid, model="whisper-large-v3", timeout=300)
    updated = manager.get_openai_asr(eid)
    assert updated["model"] == "whisper-large-v3"
    assert updated["timeout"] == 300
    assert updated["api_key"] == "sk-1234567890abcdef"

    assert manager.delete_openai_asr(eid) is True
    assert manager.list_openai_asr() == []
    assert manager.get_config()["openai_asr_id"] is None
    assert manager.delete_openai_asr(eid) is False


def test_update_masked_key_does_not_overwrite(manager):
    eid = manager.add_openai_asr("a", "https://x/v1", "sk-abcdefghijklmnop", "m")
    # 前端回显的是打码值，带 * 不应覆盖真实 key
    manager.update_openai_asr(eid, api_key="sk-a****p", model="m2")
    assert manager.get_openai_asr(eid)["api_key"] == "sk-abcdefghijklmnop"
    assert manager.get_openai_asr(eid)["model"] == "m2"


def test_public_config_masks_key(manager):
    manager.add_openai_asr("a", "https://x/v1", "sk-abcdefghijklmnop", "m")
    public = manager.get_public_config()
    assert public["openai_asr_endpoints"][0]["api_key"] != "sk-abcdefghijklmnop"
    assert "*" in public["openai_asr_endpoints"][0]["api_key"]
    # 后端内部拿到的仍是明文
    assert (
        manager.get_config()["openai_asr_endpoints"][0]["api_key"]
        == "sk-abcdefghijklmnop"
    )


def test_validation_rejects_bad_fields(manager):
    with pytest.raises(ValueError):
        manager.add_openai_asr("", "https://x/v1", "k", "m")
    with pytest.raises(ValueError):
        manager.add_openai_asr("a", "", "k", "m")
    with pytest.raises(ValueError):
        manager.add_openai_asr("a", "https://x/v1", "", "m")
    with pytest.raises(ValueError):
        manager.add_openai_asr("a", "https://x/v1", "k", "")
    with pytest.raises(ValueError):
        manager.add_openai_asr("a", "https://x/v1", "k", "m", timeout=0)
    with pytest.raises(ValueError):
        manager.add_openai_asr("a", "https://x/v1", "k", "m", chunk_size_mb=-1)


def test_delete_active_clears_selection(manager):
    a = manager.add_openai_asr("a", "https://a/v1", "k1", "m")
    b = manager.add_openai_asr("b", "https://b/v1", "k2", "m")
    manager.update_config("openai-asr", openai_asr_id=a)
    manager.delete_openai_asr(a)
    assert manager.get_config()["openai_asr_id"] is None

    manager.update_config("openai-asr", openai_asr_id=b)
    assert manager.get_config()["openai_asr_id"] == b
    assert manager.get_active_openai_asr()["id"] == b


def test_ready_gate_requires_endpoint_and_active(manager):
    manager.update_config("openai-asr")
    ready = manager.is_model_ready()
    assert ready["ready"] is False
    assert "尚未配置" in ready["reason"]

    eid = manager.add_openai_asr("a", "https://x/v1", "k", "m")
    manager.update_config("openai-asr", openai_asr_id=eid)
    assert manager.is_model_ready()["ready"] is True


def test_api_style_default_update_and_validation(manager):
    eid = manager.add_openai_asr("a", "https://x/v1", "k", "m")
    assert manager.get_openai_asr(eid)["api_style"] == "transcriptions"

    manager.update_openai_asr(eid, api_style="chat")
    assert manager.get_openai_asr(eid)["api_style"] == "chat"

    with pytest.raises(ValueError):
        manager.add_openai_asr("b", "https://x/v1", "k", "m", api_style="bogus")


def test_legacy_max_upload_mb_is_read_as_chunk_size(manager):
    """旧配置里叫 max_upload_mb，读出来要自动映射成 chunk_size_mb。"""
    manager._write({
        "transcriber_type": "openai-asr",
        "openai_asr_endpoints": [{
            "id": "legacy",
            "name": "a",
            "base_url": "https://x/v1",
            "api_key": "k",
            "model": "m",
            "max_upload_mb": 7,
        }],
    })
    endpoint = manager.get_openai_asr("legacy")
    assert endpoint["chunk_size_mb"] == 7


def test_speech_slicing_defaults_update_and_validation(manager):
    eid = manager.add_openai_asr(
        "a", "https://x/v1", "k", "mimo-v2.5-asr", api_style="chat"
    )
    endpoint = manager.get_openai_asr(eid)
    assert endpoint["max_speech_chunks"] == 120
    assert endpoint["silence_noise_db"] == -30.0
    assert endpoint["min_silence_seconds"] == 0.5

    manager.update_openai_asr(
        eid, max_speech_chunks=40, silence_noise_db=-35.0, min_silence_seconds=0.8
    )
    endpoint = manager.get_openai_asr(eid)
    assert endpoint["max_speech_chunks"] == 40
    assert endpoint["silence_noise_db"] == -35.0
    assert endpoint["min_silence_seconds"] == 0.8

    with pytest.raises(ValueError):
        manager.update_openai_asr(eid, max_speech_chunks=0)
    with pytest.raises(ValueError):
        manager.update_openai_asr(eid, min_silence_seconds=0)
