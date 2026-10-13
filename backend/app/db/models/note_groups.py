"""笔记分组（spec 007）。

用户要求分组必须持久化在数据库里（m04885 `group_storage` = 后端数据库），
并且前端不再自己存任务列表 —— 所以「有哪些组」和「哪个任务属于哪个组」
都落在后端：

* ``note_groups``：组本身（名称、排序、时间）；
* ``video_tasks.group_id``：任务到组的归属（可空 = 未分组）。

``video_tasks.group_id`` 不加外键约束：任务记录在媒体清理时可能先被删掉，
加外键会让清理流程因为一个悬垂引用而整批失败；组被删除时由
``note_group_dao`` 显式把成员置空，语义更可控。
"""
from sqlalchemy import Column, Integer, String, DateTime, func

from app.db.engine import Base


class NoteGroup(Base):
    __tablename__ = "note_groups"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    # 用户拖拽排序用的序号；新建时排在最后
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
