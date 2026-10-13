"""Persistent globally active LLM provider/model selection."""

from __future__ import annotations

from app.db.general_settings_dao import (
    get_active_model as _get_active_model,
    set_active_model as _set_active_model,
)


def get_active_model() -> dict[str, str] | None:
    active = _get_active_model() or {}
    provider_id = active.get("provider_id")
    model_name = active.get("model_name")
    if provider_id is None or not model_name:
        return None
    return {"provider_id": str(provider_id), "model_name": str(model_name)}


def set_active_model(provider_id: str, model_name: str) -> dict[str, str]:
    saved = _set_active_model(provider_id, model_name)
    return {"provider_id": str(saved["active_provider_id"]), "model_name": str(saved["active_model_name"])}


def resolve_active_model() -> dict[str, str]:
    active = get_active_model()
    if active is None:
        raise RuntimeError("尚未在通用设置中激活 LLM 模型")
    return active
