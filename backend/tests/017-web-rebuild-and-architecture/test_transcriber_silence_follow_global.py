"""端点级静音参数与「设置 → 通用」全局值的关系（2026-10-17）。

用户要的是「通用页一个开关，所有端点一起生效」。原先的实现是：保存端点时
`_normalize_endpoint` 用当时的全局值补齐三个 silence 字段并**一起写进
`config/transcriber.json`**，于是那一刻的全局值被冻结成端点值——之后改通用页
再也不会影响任何已存在的端点（实测：全局改 False/-42.0/1.25，端点仍返回
True/-30.0/0.5）。

现在改成「键不存在 = 跟随全局」：

* 新增/更新时没传的静音字段**不落盘**，读取时实时回落全局；
* 传了值才算端点级覆盖，并记进 `explicit_fields`；
* 更新时显式传 `null` = 撤销覆盖，回到跟随全局；
* 历史配置没有 `explicit_fields` 标记，三个字段一律视为未指定——端点对话框
  直到这轮才第一次出现这些控件，老值必然是自动填的默认值，不是用户选择。
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import general_settings_dao as dao
from app.db.engine import Base
from app.services import runtime_limits
from app.services.transcriber_config_manager import TranscriberConfigManager

SILENCE = ("silence_split", "silence_noise_db", "min_silence_seconds")


@pytest.fixture
def global_settings(tmp_path, monkeypatch):
    """把通用设置 DAO 指向临时库，并清掉可能干扰的环境变量。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'silence.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def _fake_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dao, "get_db", _fake_get_db)
    for name in ("ASR_SILENCE_SPLIT", "ASR_SILENCE_NOISE_DB", "ASR_MIN_SILENCE_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    runtime_limits.reset_cache()
    yield factory
    runtime_limits.reset_cache()


@pytest.fixture
def manager(tmp_path):
    return TranscriberConfigManager(filepath=str(tmp_path / "transcriber.json"))


def _add(manager, **kwargs):
    return manager.add_openai_asr(
        name="端点A",
        base_url="https://asr.example.com/v1",
        api_key="sk-test-0123456789",
        model="whisper-1",
        api_style="chat",
        **kwargs,
    )


def test_global_change_applies_when_endpoint_has_no_explicit_values(global_settings, manager):
    _add(manager)
    endpoint = manager.get_active_openai_asr()
    assert endpoint["explicit_fields"] == []
    assert endpoint["silence_split"] is True
    assert endpoint["silence_noise_db"] == -30.0
    assert endpoint["min_silence_seconds"] == 0.5

    dao.update_general_settings(
        asr_silence_split=False,
        asr_silence_noise_db=-42.0,
        asr_min_silence_seconds=1.25,
    )
    runtime_limits.reset_cache()

    endpoint = manager.get_active_openai_asr()
    assert endpoint["silence_split"] is False
    assert endpoint["silence_noise_db"] == -42.0
    assert endpoint["min_silence_seconds"] == 1.25


def test_explicit_endpoint_value_wins_over_global(global_settings, manager):
    _add(manager, silence_split=False, silence_noise_db=-38.0)
    endpoint = manager.get_active_openai_asr()
    assert endpoint["explicit_fields"] == ["silence_noise_db", "silence_split"]
    assert endpoint["silence_split"] is False
    assert endpoint["silence_noise_db"] == -38.0

    dao.update_general_settings(
        asr_silence_split=True,
        asr_silence_noise_db=-20.0,
        asr_min_silence_seconds=0.9,
    )
    runtime_limits.reset_cache()

    endpoint = manager.get_active_openai_asr()
    # 显式覆盖保持不动，未指定的字段跟着全局走
    assert endpoint["silence_split"] is False
    assert endpoint["silence_noise_db"] == -38.0
    assert endpoint["min_silence_seconds"] == 0.9


def test_null_clears_override_and_falls_back_to_global(global_settings, manager):
    endpoint_id = _add(manager, silence_split=False)
    assert manager.get_openai_asr(endpoint_id)["silence_split"] is False

    manager.update_openai_asr(endpoint_id, silence_split=None)
    endpoint = manager.get_openai_asr(endpoint_id)
    assert endpoint["silence_split"] is True
    assert "silence_split" not in endpoint["explicit_fields"]

    dao.update_general_settings(asr_silence_split=False)
    runtime_limits.reset_cache()
    assert manager.get_openai_asr(endpoint_id)["silence_split"] is False


def test_inherited_values_are_not_written_to_disk(global_settings, manager, tmp_path):
    _add(manager, silence_split=True)
    raw = json.loads((tmp_path / "transcriber.json").read_text(encoding="utf-8"))
    stored = raw["openai_asr_endpoints"][0]
    # 只有显式指定过的那一个字段落盘，其余跟随全局的不占文件
    assert stored["explicit_fields"] == ["silence_split"]
    assert stored["silence_split"] is True
    assert "silence_noise_db" not in stored
    assert "min_silence_seconds" not in stored


def test_legacy_config_without_marker_follows_global(global_settings, tmp_path):
    """历史文件里存着旧默认值、但没有 explicit_fields 标记 → 视为未指定。"""
    path = tmp_path / "transcriber.json"
    path.write_text(
        json.dumps(
            {
                "transcriber_type": "openai-asr",
                "openai_asr_id": "legacy1",
                "openai_asr_endpoints": [
                    {
                        "id": "legacy1",
                        "name": "老端点",
                        "base_url": "https://asr.example.com/v1",
                        "api_key": "sk-legacy-0123456789",
                        "model": "whisper-1",
                        "timeout": 600,
                        "chunk_size_mb": 18,
                        "api_style": "chat",
                        "max_speech_chunks": 120,
                        "silence_noise_db": -30.0,
                        "min_silence_seconds": 0.5,
                        "max_rpm": 30,
                        "chunk_concurrency": 4,
                        "silence_split": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manager = TranscriberConfigManager(filepath=str(path))
    assert manager.get_active_openai_asr()["explicit_fields"] == []

    dao.update_general_settings(asr_silence_split=False, asr_silence_noise_db=-44.0)
    runtime_limits.reset_cache()
    endpoint = manager.get_active_openai_asr()
    assert endpoint["silence_split"] is False
    assert endpoint["silence_noise_db"] == -44.0

    # 任何一次写回都要把「继承来的值」从文件里清掉，否则下次读取又会被当成显式值
    manager.update_openai_asr("legacy1", name="老端点改名")
    raw = json.loads(path.read_text(encoding="utf-8"))
    stored = raw["openai_asr_endpoints"][0]
    assert stored["name"] == "老端点改名"
    assert stored["explicit_fields"] == []
    for name in SILENCE:
        assert name not in stored, f"{name} should not be persisted"
