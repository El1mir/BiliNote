from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.services.media_resource_service import (
    cleanup_resources,
    enforce_cache_limit,
    get_cache_settings,
    get_retention_settings,
    get_recent_cleanup_runs,
    preview_cache_limit,
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
    resource_types: list[str] = Field(
        default_factory=lambda: ["screenshot", "video", "audio"]
    )
    expired_only: bool = True


def _validate_types(resource_types: list[str]) -> bool:
    return bool(resource_types) and set(resource_types) <= {
        "screenshot",
        "video",
        "audio",
    }


@router.get("/settings")
def read_retention_settings():
    return R.success(get_retention_settings())


@router.put("/settings")
def write_retention_settings(data: RetentionRequest):
    return R.success(
        set_retention_settings(
            data.screenshot_retention_days, data.media_retention_days
        )
    )


@router.get("/cleanup/recent")
def read_recent_cleanup_runs():
    return R.success(get_recent_cleanup_runs())


@router.get("/cleanup/preview")
def read_cleanup_preview(
    resource_types: str = "screenshot,video,audio", expired_only: bool = True
):
    kinds = [item.strip() for item in resource_types.split(",") if item.strip()]
    if not _validate_types(kinds):
        return R.error("资源类别无效", code=400)
    return R.success(preview_cleanup(kinds, expired_only))


@router.post("/cleanup")
async def run_cleanup(data: CleanupRequest):
    if not _validate_types(data.resource_types):
        return R.error("资源类别无效", code=400)
    preview = await run_in_threadpool(
        preview_cleanup, data.resource_types, data.expired_only
    )
    report = await run_in_threadpool(
        cleanup_resources, data.resource_types, data.expired_only
    )
    return R.success({"scheduled": False, "preview": preview, "result": report})


# ---------------------------------------------------------------------------
# 容量维度（spec 007 §12 / spec 009 ticket 07）
#
# 这里只提供**观测**与**手动触发**：缓存上限本身的读写在通用设置页
# （`general_settings` / `app/db/general_settings_dao.py`），不在这里重复定义字段 ——
# 否则同一个值会有两个写入入口，前端和后台清理器看到的就未必是同一份配置。
# ---------------------------------------------------------------------------


@router.get("/cache/limit")
async def read_cache_limit():
    """只读观测：当前受管缓存总占用 / 上限 / 若触发会删多少。

    返回的 `settings` 是清理器实际生效的设置（含缺失键的兜底默认值），方便前端
    在设置页之外做一次交叉核对；写入仍走通用设置接口。
    """
    settings = await run_in_threadpool(get_cache_settings)
    report = await run_in_threadpool(preview_cache_limit)
    return R.success({"settings": settings, "report": report})


@router.post("/cache/enforce")
async def run_cache_enforce():
    """手动触发一次容量边界清理（同步执行，可能较慢）。

    清理本身是同步阻塞的（扫目录 + 删文件），所以走线程池而不是直接 await；
    正式路径仍由 `media_cleanup_loop` 每小时一轮 + 任务终态钩子负责，这个端点
    只是给运维/调试一个「现在立刻收一次」的入口。
    """
    report = await run_in_threadpool(enforce_cache_limit)
    return R.success(report)
