"""笔记分组的读写（spec 007）。

用户决策（m04885 / m04951）：分组与「哪个任务属于哪个组」都持久化在后端数据库，
前端不再自己存任务列表。本模块负责组本身的 CRUD + 任务归属。

设计取舍
--------
* 组的 ``id`` 用 uuid hex，前端拖拽时直接带着它调接口。
* ``position`` 只用于排序，新建时取「当前最大值 + 1」，排在最后。没有做完整的
  重排接口 —— 用户要的是「新建/删除/拖动任务进出组」，没要求拖动排序组。
* 删除组时把组内任务的 ``group_id`` 置为 NULL（回到「未分组」），**不删任务**。
  用户删除一个组时的心理预期是「这个分组没了」，不是「里面的笔记也没了」。
  spec 010 之后这条仍是**默认**行为，但路由层多了一个显式 ``delete_tasks=True``：
  那时先逐个 ``delete_task_completely`` 再删组。删除动作刻意**不放在本模块** ——
  ``db/`` 层不该 import ``services/``；本模块只负责「解绑 + 删组」。
* 所有函数都返回**普通 dict / int**，不把 ORM 实例泄漏给上层：Session 在
  ``finally`` 里就关掉了，游离实例的属性访问会触发 DetachedInstanceError。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from app.db.engine import get_db
from app.db.models.note_groups import NoteGroup
from app.db.models.video_tasks import VideoTask
from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 组名长度上限，防止前端塞进一整段文本把列表撑爆。
MAX_GROUP_NAME_LENGTH = 64

#: 组数量上限。
#:
#: spec 009 起批量提交**每批必建一个新组**（用户决策 m00203），所以这个上限不再
#: 只是「人工整理能用多少组」的问题：一天跑几批、连着跑几周就会撞到它。200 太紧，
#: 改成 1000。撞到上限时 ``create_group`` 抛 ``NoteGroupError``，批量入口会把它
#: 转成明确的错误响应（code 300105）—— 绝不静默退回「未分组」。
MAX_GROUPS = 1000


class NoteGroupError(ValueError):
    """调用方传了不合法的分组参数。"""


def _clean_name(name: Any) -> str:
    text = str(name or "").strip()
    if not text:
        raise NoteGroupError("分组名称不能为空")
    if len(text) > MAX_GROUP_NAME_LENGTH:
        raise NoteGroupError(f"分组名称不能超过 {MAX_GROUP_NAME_LENGTH} 个字符")
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _serialize(row: NoteGroup, task_count: Optional[int] = None) -> Dict[str, Any]:
    """把组行拍成普通 dict（不返回 ORM 实例）。"""
    data: Dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "position": _safe_int(row.position, 0),
    }
    if task_count is not None:
        data["task_count"] = _safe_int(task_count, 0)
    return data


def list_groups() -> List[Dict[str, Any]]:
    """按 position 升序返回所有组，并带上每组的任务数。"""
    db = next(get_db())
    try:
        rows = (
            # pi-lens-ignore: python-sql-injection
            db.query(NoteGroup)
            .order_by(NoteGroup.position.asc(), NoteGroup.created_at.asc())
            .all()
        )
        count_rows = (
            # pi-lens-ignore: python-sql-injection
            db.query(VideoTask.group_id, func.count(VideoTask.id))
            .filter(VideoTask.group_id.isnot(None))
            .group_by(VideoTask.group_id)
            .all()
        )
        counts = {row[0]: _safe_int(row[1], 0) for row in count_rows}
        return [_serialize(row, counts.get(row.id, 0)) for row in rows]
    finally:
        db.close()


def create_group(name: Any) -> Dict[str, Any]:
    """新建一个组，排在最后。"""
    cleaned = _clean_name(name)
    db = next(get_db())
    try:
        # pi-lens-ignore: python-sql-injection
        if db.query(NoteGroup).count() >= MAX_GROUPS:
            raise NoteGroupError(f"分组数量已达上限（{MAX_GROUPS}）")
        max_position = (
            db.query(NoteGroup.position).order_by(NoteGroup.position.desc()).first()
        )
        next_position = _safe_int(max_position[0] if max_position else None, 0) + 1
        row = NoteGroup(id=uuid.uuid4().hex, name=cleaned, position=next_position)
        db.add(row)
        db.commit()
        db.refresh(row)
        logger.info("新建笔记分组：%s（%s）", cleaned, row.id)
        return _serialize(row, 0)
    finally:
        db.close()


def rename_group(group_id: str, name: Any) -> Dict[str, Any]:
    cleaned = _clean_name(name)
    db = next(get_db())
    try:
        # pi-lens-ignore: python-sql-injection
        row = db.query(NoteGroup).filter_by(id=group_id).first()
        if row is None:
            raise NoteGroupError("分组不存在")
        # 用 setattr 而不是 row.name = cleaned：声明式模型的属性在类型层面是
        # Column[str]，直接赋值会被 pyright 报 reportAttributeAccessIssue。
        # 这是本仓库既有写法（见 provider_dao.py 的 update_provider）。
        setattr(row, "name", cleaned)
        db.commit()
        db.refresh(row)
        return _serialize(row)
    finally:
        db.close()


def delete_group(group_id: str) -> int:
    """删除组，并把组内任务退回未分组；返回受影响的成员数。"""
    db = next(get_db())
    try:
        # pi-lens-ignore: python-sql-injection
        row = db.query(NoteGroup).filter_by(id=group_id).first()
        if row is None:
            raise NoteGroupError("分组不存在")
        # 先解除归属再删组：任务本身保留，只是回到「未分组」。
        affected = (
            # pi-lens-ignore: python-sql-injection
            db.query(VideoTask)
            .filter_by(group_id=group_id)
            .update({"group_id": None}, synchronize_session=False)
        )
        db.delete(row)
        db.commit()
        logger.info(
            "删除笔记分组 %s，%d 个任务退回未分组", group_id, _safe_int(affected)
        )
        return _safe_int(affected)
    finally:
        db.close()


def get_task_group(task_id: str) -> Optional[str]:
    db = next(get_db())
    try:
        # pi-lens-ignore: python-sql-injection
        row = db.query(VideoTask).filter_by(task_id=task_id).first()
        if row is None:
            return None
        value = row.group_id
        # 显式跟 None 比较，不要写 `if value`：声明式属性在类型层面是
        # Column[str]，真值判断会被 pyright 判为无效条件（Column 没有 __bool__）。
        return str(value) if value is not None else None
    finally:
        db.close()


def assign_task_to_group(task_id: str, group_id: Optional[str]) -> None:
    """把任务移进/移出分组。``group_id=None`` 表示移出（未分组）。"""
    db = next(get_db())
    try:
        # pi-lens-ignore: python-sql-injection
        row = db.query(VideoTask).filter_by(task_id=task_id).first()
        if row is None:
            raise NoteGroupError("任务不存在")
        if group_id:
            # pi-lens-ignore: python-sql-injection
            exists = db.query(NoteGroup).filter_by(id=group_id).first()
            if exists is None:
                raise NoteGroupError("分组不存在")
        # setattr 而非 row.group_id = ...：同 rename_group，绕开 Column[str] 赋值告警。
        setattr(row, "group_id", group_id or None)
        db.commit()
    finally:
        db.close()


def assign_tasks_to_group(task_ids: List[str], group_id: Optional[str]) -> int:
    """批量移入/移出分组，返回实际改动的任务数。"""
    cleaned = [str(item).strip() for item in (task_ids or []) if str(item).strip()]
    if not cleaned:
        return 0
    db = next(get_db())
    try:
        if group_id:
            # pi-lens-ignore: python-sql-injection
            exists = db.query(NoteGroup).filter_by(id=group_id).first()
            if exists is None:
                raise NoteGroupError("分组不存在")
        affected = (
            # pi-lens-ignore: python-sql-injection
            db.query(VideoTask)
            .filter(VideoTask.task_id.in_(cleaned))
            .update({"group_id": group_id or None}, synchronize_session=False)
        )
        db.commit()
        return _safe_int(affected)
    finally:
        db.close()


def list_task_ids_in_group(group_id: Optional[str]) -> List[str]:
    """取某个组（``None`` = 未分组）里的全部 task_id。"""
    db = next(get_db())
    try:
        query = db.query(VideoTask.task_id)
        if group_id:
            query = query.filter(VideoTask.group_id == group_id)
        else:
            query = query.filter(VideoTask.group_id.is_(None))
        return [str(row[0]) for row in query.all() if row[0]]
    finally:
        db.close()
