# app/routers/general.py
"""General settings and globally active LLM selection."""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.general_settings_dao import get_general_settings, update_general_settings
from app.services.active_model import get_active_model, set_active_model
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R

logger = get_logger(__name__)
router = APIRouter(prefix="/general", tags=["general"])


class GeneralSettingsRequest(BaseModel):
    max_parallel_notes: Optional[int] = None
    cache_limit_bytes: Optional[int] = None
    min_free_disk_bytes: Optional[int] = None
    circuit_breaker_threshold: Optional[int] = None


class ActiveModelRequest(BaseModel):
    provider_id: str
    model_name: str


@router.get("/settings")
def read_general_settings():
    try:
        settings = get_general_settings()
        settings["active_model"] = get_active_model()
        return R.success(settings)
    except Exception as exc:
        logger.exception("读取通用设置失败")
        return R.error(f"读取通用设置失败：{exc}", code=500)


@router.post("/settings")
def write_general_settings(data: GeneralSettingsRequest):
    try:
        return R.success(update_general_settings(
            max_parallel_notes=data.max_parallel_notes,
            cache_limit_bytes=data.cache_limit_bytes,
            min_free_disk_bytes=data.min_free_disk_bytes,
            circuit_breaker_threshold=data.circuit_breaker_threshold,
        ))
    except Exception as exc:
        logger.exception("保存通用设置失败")
        return R.error(f"保存通用设置失败：{exc}", code=500)


@router.post("/active_model")
def activate_model(data: ActiveModelRequest):
    try:
        return R.success(set_active_model(data.provider_id, data.model_name))
    except ValueError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("激活 LLM 模型失败")
        return R.error(f"激活 LLM 模型失败：{exc}", code=500)
