"""通用设置的读写（spec 007；缓存边界字段见 spec 009 / ticket 07）。

单行表：不存在就建，存在就更新。读不到时一律回落到默认值，绝不抛异常 ——
这个值决定「同时能跑几个笔记任务」，读失败必须退化到保守的默认值而不是让
生成入口整个挂掉。同样的理由适用于 ticket 07 新增的三个缓存边界字段：它们
决定媒体清理和熔断行为，读不到数据库时必须各自回落默认值，而不是 500。
"""

from __future__ import annotations

from typing import Any, Dict

from app.db.engine import get_db
from app.db.models.general_settings import (
    DEFAULT_CACHE_LIMIT_BYTES,
    DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    DEFAULT_MAX_PARALLEL_NOTES,
    DEFAULT_MIN_FREE_DISK_BYTES,
    MAX_CACHE_LIMIT_BYTES,
    MAX_CIRCUIT_BREAKER_THRESHOLD,
    MAX_MIN_FREE_DISK_BYTES,
    MAX_PARALLEL_NOTES_LIMIT,
    GeneralSettings,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def normalize_max_parallel_notes(value: Any) -> int:
    """把任意输入收敛到 [1, MAX_PARALLEL_NOTES_LIMIT]。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_PARALLEL_NOTES
    if parsed < 1:
        return 1
    return min(parsed, MAX_PARALLEL_NOTES_LIMIT)


def normalize_cache_limit_bytes(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_CACHE_LIMIT_BYTES]。

    ``0`` 是**有意义**的取值（表示「不限缓存大小」），不是「没设置」，所以
    这里不能像并行度那样把 0 抬到 1 —— 负数和垃圾输入才回落到默认的 10 GiB。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CACHE_LIMIT_BYTES
    if parsed < 0:
        return DEFAULT_CACHE_LIMIT_BYTES
    return min(parsed, MAX_CACHE_LIMIT_BYTES)


def normalize_min_free_disk_bytes(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_MIN_FREE_DISK_BYTES]。

    ``0`` = 不做磁盘门禁（用户明确要求「剩多少都照跑」）。负数是无效输入，
    回落到默认的 5 GiB —— 注意这里**不能**把负数当成 0，否则手滑输错会把
    保护静默关掉。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MIN_FREE_DISK_BYTES
    if parsed < 0:
        return DEFAULT_MIN_FREE_DISK_BYTES
    return min(parsed, MAX_MIN_FREE_DISK_BYTES)


def normalize_circuit_breaker_threshold(value: Any) -> int:
    """把任意输入收敛到 [0, MAX_CIRCUIT_BREAKER_THRESHOLD]。

    ``0`` = 关闭熔断（供应商一直挂也继续派发）。负数同样视为无效输入回落默认
    值 5：负数在语义上没有意义（「失败 -1 次就熔断」），当成 0 会让用户以为
    自己关掉了熔断，实际却是静默打开了默认阈值。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    if parsed < 0:
        return DEFAULT_CIRCUIT_BREAKER_THRESHOLD
    return min(parsed, MAX_CIRCUIT_BREAKER_THRESHOLD)


def _get_or_create(db) -> GeneralSettings:
    from app.db.engine import get_engine
    from app.db.init_db import init_db

    if db.get_bind() is get_engine():
        init_db()
    # pi-lens-ignore: python-sql-injection
    row = db.query(GeneralSettings).filter_by(id=1).first()
    if row is None:
        row = GeneralSettings(id=1, max_parallel_notes=DEFAULT_MAX_PARALLEL_NOTES)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _serialize(row: GeneralSettings) -> Dict[str, Any]:
    """把单行设置摊平成响应 dict。

    每个可调字段都同时返回「当前值」和「上限 / 默认值」，前端不用把常量再抄
    一遍（抄了就会跟后端漂移）。所有值都过 normalize：老库里这三列可能是 NULL
    （ALTER TABLE 加的列、或者迁移前写入的行），normalize 负责把 None 变成默认值。
    """
    return {
        "max_parallel_notes": normalize_max_parallel_notes(row.max_parallel_notes),
        "max_parallel_notes_limit": MAX_PARALLEL_NOTES_LIMIT,
        "cache_limit_bytes": normalize_cache_limit_bytes(row.cache_limit_bytes),
        "cache_limit_bytes_default": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_limit": MAX_CACHE_LIMIT_BYTES,
        "min_free_disk_bytes": normalize_min_free_disk_bytes(row.min_free_disk_bytes),
        "min_free_disk_bytes_default": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_limit": MAX_MIN_FREE_DISK_BYTES,
        "circuit_breaker_threshold": normalize_circuit_breaker_threshold(
            row.circuit_breaker_threshold
        ),
        "circuit_breaker_threshold_default": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_limit": MAX_CIRCUIT_BREAKER_THRESHOLD,
        "active_provider_id": str(row.active_provider_id) if row.active_provider_id is not None else None,
        "active_model_name": row.active_model_name,
    }


def _default_payload() -> Dict[str, Any]:
    """读库失败时的兜底响应，形状必须与 _serialize 完全一致。"""
    return {
        "max_parallel_notes": DEFAULT_MAX_PARALLEL_NOTES,
        "max_parallel_notes_limit": MAX_PARALLEL_NOTES_LIMIT,
        "cache_limit_bytes": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_default": DEFAULT_CACHE_LIMIT_BYTES,
        "cache_limit_bytes_limit": MAX_CACHE_LIMIT_BYTES,
        "min_free_disk_bytes": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_default": DEFAULT_MIN_FREE_DISK_BYTES,
        "min_free_disk_bytes_limit": MAX_MIN_FREE_DISK_BYTES,
        "circuit_breaker_threshold": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_default": DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
        "circuit_breaker_threshold_limit": MAX_CIRCUIT_BREAKER_THRESHOLD,
        "active_provider_id": None,
        "active_model_name": None,
    }


def get_general_settings() -> Dict[str, Any]:
    db = next(get_db())
    try:
        row = _get_or_create(db)
        return _serialize(row)
    except Exception as exc:  # noqa: BLE001 - 读不到就用默认值，别拖垮调用方
        logger.error("读取通用设置失败，回退到默认值：%s", exc)
        return _default_payload()
    finally:
        db.close()


def get_active_model() -> Dict[str, Any]:
    settings = get_general_settings()
    return {
        "provider_id": settings.get("active_provider_id"),
        "model_name": settings.get("active_model_name"),
    }


def set_active_model(provider_id: str, model_name: str) -> Dict[str, Any]:
    normalized_provider_id = str(provider_id).strip() if provider_id is not None else ""
    if not normalized_provider_id:
        raise ValueError("供应商 ID 无效")
    if not model_name.strip():
        raise ValueError("模型名不能为空")
    from app.db.model_dao import get_models_by_provider
    from app.db.provider_dao import get_provider_by_id

    provider = get_provider_by_id(normalized_provider_id)
    if provider is None or int(provider.enabled or 0) != 1:
        raise ValueError("所选供应商不存在或未启用")
    models = get_models_by_provider(normalized_provider_id)
    if not any(model.get("model_name") == model_name.strip() for model in models):
        raise ValueError("所选模型不属于该供应商")

    db = next(get_db())
    try:
        row = _get_or_create(db)
        setattr(row, "active_provider_id", normalized_provider_id)
        setattr(row, "active_model_name", model_name.strip())
        db.commit()
        db.refresh(row)
        return _serialize(row)
    finally:
        db.close()


def get_max_parallel_notes() -> int:
    """只要那一个数字时的快捷方式（生成入口每个任务都要读一次）。"""
    # 走 normalize 而不是裸 int()：这个值决定并发闸门，任何异常都必须退化到
    # 默认值。get_general_settings() 已经保证返回可解析的值，normalize 是第二道保险。
    return normalize_max_parallel_notes(
        get_general_settings().get("max_parallel_notes")
    )


def update_general_settings(
    max_parallel_notes: Any = None,
    cache_limit_bytes: Any = None,
    min_free_disk_bytes: Any = None,
    circuit_breaker_threshold: Any = None,
) -> Dict[str, Any]:
    """部分更新：只有**显式传入**（非 None）的字段会被改写，其余保持原值。

    ``None`` 表示「这次没传这个字段」，不是「把它设成空」—— 前端设置页是按需
    提交的（比如只调并行度），若把未传的字段当成清空，用户改一项就会把另外三项
    悄悄重置。三个缓存边界字段的 0 值不受影响：0 是合法的显式取值，用
    ``is not None`` 判断能正确区分。
    """
    db = next(get_db())
    try:
        row = _get_or_create(db)
        # setattr 而非 row.max_parallel_notes = ...：声明式属性在类型层面是
        # Column[int]，直接赋值会被 pyright 报 reportAttributeAccessIssue。
        # 这是本仓库既有写法（见 provider_dao.py 的 update_provider）。
        if max_parallel_notes is not None:
            setattr(
                row,
                "max_parallel_notes",
                normalize_max_parallel_notes(max_parallel_notes),
            )
        if cache_limit_bytes is not None:
            setattr(
                row,
                "cache_limit_bytes",
                normalize_cache_limit_bytes(cache_limit_bytes),
            )
        if min_free_disk_bytes is not None:
            setattr(
                row,
                "min_free_disk_bytes",
                normalize_min_free_disk_bytes(min_free_disk_bytes),
            )
        if circuit_breaker_threshold is not None:
            setattr(
                row,
                "circuit_breaker_threshold",
                normalize_circuit_breaker_threshold(circuit_breaker_threshold),
            )
        db.commit()
        db.refresh(row)
        return _serialize(row)
    finally:
        db.close()
