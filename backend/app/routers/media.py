from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.services.media_resource_service import (
    cleanup_resources,
    get_retention_settings,
    get_recent_cleanup_runs,
    preview_cleanup,
    set_retention_settings,
)
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R

router = APIRouter(prefix="/media", tags=["media"])
logger = get_logger(__name__)


class RetentionRequest(BaseModel):
    screenshot_retention_days: int = Field(ge=0, le=36500)
    media_retention_days: int = Field(ge=0, le=36500)


class CleanupRequest(BaseModel):
    resource_types: list[str] = Field(default_factory=lambda: ["screenshot", "video", "audio"])
    expired_only: bool = True


def _validate_types(resource_types: list[str]) -> bool:
    return bool(resource_types) and set(resource_types) <= {"screenshot", "video", "audio"}


@router.get("/settings")
def read_retention_settings():
    return R.success(get_retention_settings())


@router.put("/settings")
def write_retention_settings(data: RetentionRequest):
    return R.success(set_retention_settings(data.screenshot_retention_days, data.media_retention_days))


@router.get("/cleanup/recent")
def read_recent_cleanup_runs():
    return R.success(get_recent_cleanup_runs())


@router.get("/cleanup/preview")
def read_cleanup_preview(resource_types: str = "screenshot,video,audio", expired_only: bool = True):
    kinds = [item.strip() for item in resource_types.split(",") if item.strip()]
    if not _validate_types(kinds):
        return R.error("资源类别无效", code=400)
    return R.success(preview_cleanup(kinds, expired_only))


@router.post("/cleanup")
async def run_cleanup(data: CleanupRequest):
    if not _validate_types(data.resource_types):
        return R.error("资源类别无效", code=400)
    preview = await run_in_threadpool(preview_cleanup, data.resource_types, data.expired_only)
    report = await run_in_threadpool(cleanup_resources, data.resource_types, data.expired_only)
    return R.success({"scheduled": False, "preview": preview, "result": report})
