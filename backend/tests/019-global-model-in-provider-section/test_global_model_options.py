"""全局模型只在「模型提供商」页选择，且失效指针必须自行消失（spec 019）。

原始实现（tests/013-global-active-model）只验证了「存得下、读得回」；这里补的是
用户实际撞到的行为：**供应商里把模型删掉之后，通用设置里的当前全局模型还在**。
所以断言重点在「读路径校验 + 删模型时清指针 + 候选只来自启用供应商」。
"""

import pytest
from app.db import engine as engine_module
from app.db.models.general_settings import GeneralSettings  # noqa: F401
from app.db.models.models import Model
from app.db.models.providers import Provider
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'global-model-019.db'}")
    engine_module.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)
    with factory() as db:
        db.add(
            Provider(
                id="7",
                name="启用供应商",
                logo="",
                type="openai",
                api_key="key",
                base_url="https://a.example.com",
                enabled=1,
            )
        )
        db.add(Model(provider_id="7", model_name="good-model"))
        db.add(Model(provider_id="7", model_name="spare-model"))
        db.add(
            Provider(
                id="8",
                name="停用供应商",
                logo="",
                type="openai",
                api_key="key",
                base_url="https://b.example.com",
                enabled=0,
            )
        )
        db.add(Model(provider_id="8", model_name="disabled-model"))
        db.add(
            Provider(
                id="9",
                name="空供应商",
                logo="",
                type="openai",
                api_key="key",
                base_url="https://c.example.com",
                enabled=1,
            )
        )
        db.commit()
    return engine


def test_candidates_come_only_from_enabled_providers_that_have_models(db_env):
    from app.services.active_model import list_global_model_options, set_active_model

    set_active_model("7", "good-model")
    options = list_global_model_options()

    assert [p["provider_id"] for p in options["providers"]] == ["7"]
    assert options["providers"][0]["provider_name"] == "启用供应商"
    assert [m["model_name"] for m in options["providers"][0]["models"]] == [
        "good-model",
        "spare-model",
    ]
    assert options["active"] == {"provider_id": "7", "model_name": "good-model"}


def test_disabled_provider_never_appears_as_a_candidate(db_env):
    from app.services.active_model import list_global_model_options

    names = [
        m["model_name"]
        for p in list_global_model_options()["providers"]
        for m in p["models"]
    ]

    assert "disabled-model" not in names


def test_deleted_model_clears_the_pointer_immediately(db_env):
    """用户的原始问题：供应商里删了模型，全局模型不该还留着。"""
    from app.db.model_dao import get_models_by_provider
    from app.services.active_model import get_active_model, set_active_model
    from app.services.model import ModelService

    set_active_model("7", "good-model")
    model_id = next(
        m["id"] for m in get_models_by_provider("7") if m["model_name"] == "good-model"
    )

    assert ModelService.delete_model_by_id(model_id) is True

    assert get_active_model() is None
    from app.db.general_settings_dao import get_general_settings

    settings = get_general_settings()
    assert settings["active_provider_id"] is None
    assert settings["active_model_name"] is None


def test_stale_pointer_is_dropped_even_without_the_delete_hook(db_env):
    """绕过删除钩子直接改库（老数据、手工改库、别的进程）时，读路径仍要自愈。"""
    from app.db.general_settings_dao import get_general_settings
    from app.db.model_dao import delete_model, get_models_by_provider
    from app.services.active_model import get_active_model, set_active_model

    set_active_model("7", "spare-model")
    delete_model(
        next(
            m["id"]
            for m in get_models_by_provider("7")
            if m["model_name"] == "spare-model"
        )
    )

    assert get_active_model() is None
    assert get_general_settings()["active_model_name"] is None


def test_disabling_the_provider_invalidates_the_pointer(db_env):
    from app.db.provider_dao import update_provider
    from app.services.active_model import get_active_model, set_active_model

    set_active_model("7", "good-model")
    update_provider("7", enabled=0)

    assert get_active_model() is None


def test_resolve_message_points_at_the_provider_page(db_env):
    from app.services.active_model import resolve_active_model

    with pytest.raises(RuntimeError, match="尚未在模型提供商中激活全局模型"):
        resolve_active_model()
