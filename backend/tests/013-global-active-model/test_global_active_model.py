"""Global active-model persistence and request-scoped compatibility tests."""

import pytest
from app.db import engine as engine_module
from app.db.models.general_settings import GeneralSettings  # noqa: F401
from app.db.models.models import Model
from app.db.models.providers import Provider
from app.services.active_model import (
    get_active_model,
    resolve_active_model,
    set_active_model,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'global-model.db'}")
    engine_module.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(engine_module, "SessionLocal", factory)
    with factory() as db:
        db.add(
            Provider(
                id="7",
                name="Provider",
                logo="",
                type="openai",
                api_key="key",
                base_url="https://example.com",
                enabled=1,
            )
        )
        db.add(Model(provider_id="7", model_name="new-model"))
        db.add(
            Provider(
                id="3",
                name="Old Provider",
                logo="",
                type="openai",
                api_key="key",
                base_url="https://example.com",
                enabled=1,
            )
        )
        db.add(Model(provider_id="3", model_name="old-model"))
        db.commit()
    return engine


def test_active_model_selection_persists_and_resolves(db_env):
    selected = set_active_model("7", "new-model")

    assert selected == {"provider_id": "7", "model_name": "new-model"}
    assert get_active_model() == selected
    assert resolve_active_model() == selected


def test_missing_active_model_fails_instead_of_guessing(db_env):
    with pytest.raises(RuntimeError, match="尚未在模型提供商中激活全局模型"):
        resolve_active_model()


def test_reselection_replaces_old_provider_and_model(db_env):
    set_active_model("3", "old-model")
    set_active_model("7", "new-model")

    assert resolve_active_model() == {"provider_id": "7", "model_name": "new-model"}
    from app.db.general_settings_dao import get_general_settings

    settings = get_general_settings()
    assert settings["active_provider_id"] == "7"
    assert settings["active_model_name"] == "new-model"


def test_legacy_request_model_fields_are_never_persisted_or_executed():
    from app.enmus.note_enums import DownloadQuality
    from app.routers.note import VideoRequest, _build_task_kwargs, _payload_for_storage

    request = VideoRequest(
        video_url="https://www.bilibili.com/video/BV1xx411c7mD",
        platform="bilibili",
        quality=DownloadQuality.fast,
        model_name="old-model",
        provider_id="3",
    )
    kwargs = _build_task_kwargs(
        "task-1", request.video_url, request.platform, request, None
    )
    stored = _payload_for_storage(kwargs)

    assert "model_name" not in kwargs
    assert "provider_id" not in kwargs
    assert "model_name" not in stored
    assert "provider_id" not in stored
