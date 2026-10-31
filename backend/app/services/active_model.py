"""全局模型（provider + model）的唯一入口。

这个指针现在**只在「模型提供商」页**选择（spec 019）：它指向「启用供应商下的某个
模型」，所以读路径必须校验它是否还有效 —— 供应商被停用、模型被删掉之后，旧指针
不能继续冒充全局模型，否则任务会带着一个已经不存在的模型名去请求网关（用户看到
的现象就是「供应商里删了，通用设置里还写着」）。
"""

from __future__ import annotations

from typing import Any, cast

from app.db.general_settings_dao import (
    clear_active_model as _clear_active_model,
)
from app.db.general_settings_dao import (
    get_active_model as _get_active_model,
)
from app.db.general_settings_dao import (
    set_active_model as _set_active_model,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

NO_ACTIVE_MODEL_MESSAGE = "尚未在模型提供商中激活全局模型"


def _model_still_exists(provider_id: str, model_name: str) -> bool:
    """指针是否还指向「启用供应商下的真实模型」。"""
    from app.db.model_dao import get_models_by_provider
    from app.db.provider_dao import get_provider_by_id

    provider = get_provider_by_id(provider_id)
    # cast：Provider 是 SQLAlchemy 声明式模型，列在静态检查里是 Column[int]，
    # 运行期拿到的就是 1/0 —— 不 cast 会被判成「ColumnElement[bool] 不能当条件用」。
    if provider is None or cast(int, provider.enabled) != 1:
        return False
    return any(
        model.get("model_name") == model_name
        for model in get_models_by_provider(provider_id)
    )


def get_active_model() -> dict[str, str] | None:
    active = _get_active_model() or {}
    provider_id = active.get("provider_id")
    model_name = active.get("model_name")
    if provider_id is None or not model_name:
        return None
    selection = {"provider_id": str(provider_id), "model_name": str(model_name)}
    if not _model_still_exists(selection["provider_id"], selection["model_name"]):
        _clear_active_model()
        logger.warning(
            "全局模型已失效并清除：provider=%s model=%s",
            selection["provider_id"],
            selection["model_name"],
        )
        return None
    return selection


def set_active_model(provider_id: str, model_name: str) -> dict[str, str]:
    saved = _set_active_model(provider_id, model_name)
    return {
        "provider_id": str(saved["active_provider_id"]),
        "model_name": str(saved["active_model_name"]),
    }


def resolve_active_model() -> dict[str, str]:
    active = get_active_model()
    if active is None:
        raise RuntimeError(NO_ACTIVE_MODEL_MESSAGE)
    return active


def clear_active_model_if_matches(provider_id: Any, model_name: Any) -> bool:
    """模型被删掉时顺手清指针，不等下一次读才发现。"""
    active = _get_active_model() or {}
    if str(active.get("provider_id") or "") != str(provider_id or ""):
        return False
    if str(active.get("model_name") or "") != str(model_name or ""):
        return False
    return _clear_active_model()


def list_global_model_options() -> dict[str, Any]:
    """启用供应商 + 其下模型：前端「模型提供商」页据此渲染全局模型选择器。

    只列启用供应商：停用的供应商不会被真正调用，列进候选等于给出一个假选项。
    没有模型的供应商也跳过，避免列表里出现一对空分组。
    """
    from app.db.model_dao import get_models_by_provider
    from app.db.provider_dao import get_enabled_providers

    providers = []
    for provider in get_enabled_providers():
        models = get_models_by_provider(cast(str, provider.id))
        if not models:
            continue
        providers.append(
            {
                "provider_id": str(cast(str, provider.id)),
                "provider_name": cast(str, provider.name),
                "models": [
                    {"id": model["id"], "model_name": model["model_name"]}
                    for model in models
                ],
            }
        )
    return {"active": get_active_model(), "providers": providers}
