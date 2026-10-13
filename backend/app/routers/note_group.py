# app/routers/note_group.py
"""笔记分组的 HTTP 接口（spec 007）。

分组与任务归属都持久化在后端数据库（用户决策 m04951：「前端不要做数据储存了，
前端 db 直接移除换到后端」）。本路由只做参数校验与响应包装，真正的读写逻辑全部
在 :mod:`app.db.note_group_dao` 里。

关于「未分组」：它不是一个真实的行，而是 ``group_id IS NULL`` 的虚拟区。
列表接口会把它作为 ``group_id=None`` 的一项单独返回，这样前端拖拽时不用特判。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.note_group_dao import (
    MAX_GROUPS,
    MAX_GROUP_NAME_LENGTH,
    NoteGroupError,
    assign_task_to_group,
    assign_tasks_to_group,
    create_group,
    delete_group,
    list_groups,
    rename_group,
)
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R

logger = get_logger(__name__)

router = APIRouter(prefix="/note_group", tags=["note_group"])

#: 「未分组」虚拟区在前端的固定标识。真实组的 id 是 uuid hex，不会撞上这个值。
UNGROUPED_ID = "__ungrouped__"


class GroupRequest(BaseModel):
    name: str


class GroupRenameRequest(BaseModel):
    group_id: str
    name: str


class GroupDeleteRequest(BaseModel):
    """删除分组。``delete_tasks=True`` 时连组内任务一起彻底删除（spec 010）。"""

    group_id: str
    delete_tasks: bool = False


class TaskGroupRequest(BaseModel):
    """单个任务移入/移出分组。``group_id`` 为空 = 移出（回到未分组）。"""

    task_id: str
    group_id: Optional[str] = None


class TasksGroupRequest(BaseModel):
    """批量移入/移出分组（前端多选拖拽）。"""

    task_ids: list[str]
    group_id: Optional[str] = None


def _normalize_group_id(value: Optional[str]) -> Optional[str]:
    """把「未分组」的各种写法统一成 ``None``。

    前端既可能传 ``null``，也可能传虚拟区的哨兵值；两者都必须落到
    ``group_id IS NULL``，否则会把任务挂到一个叫 ``__ungrouped__`` 的假组上。
    """
    text = str(value or "").strip()
    if not text or text == UNGROUPED_ID:
        return None
    return text


@router.get("")
def get_groups():
    """列出所有分组（按 position 升序），外加「未分组」虚拟区的成员数。"""
    try:
        groups = list_groups()
        # 未分组的数量不在 list_groups 里（它不是真实的行），单独数一次。
        from app.db.note_group_dao import list_task_ids_in_group

        ungrouped = len(list_task_ids_in_group(None))
        return R.success(
            {
                "groups": groups,
                "ungrouped_id": UNGROUPED_ID,
                "ungrouped_count": ungrouped,
                "max_groups": MAX_GROUPS,
                "max_name_length": MAX_GROUP_NAME_LENGTH,
            }
        )
    except Exception as exc:
        logger.exception("列出笔记分组失败")
        return R.error(f"列出笔记分组失败：{exc}", code=500)


@router.post("")
def post_group(data: GroupRequest):
    """新建分组。"""
    try:
        group = create_group(data.name)
        return R.success({"group": group})
    except NoteGroupError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("新建笔记分组失败")
        return R.error(f"新建笔记分组失败：{exc}", code=500)


@router.post("/rename")
def post_rename(data: GroupRenameRequest):
    """重命名分组。"""
    try:
        group = rename_group(data.group_id, data.name)
        return R.success({"group": group})
    except NoteGroupError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("重命名笔记分组失败")
        return R.error(f"重命名笔记分组失败：{exc}", code=500)


@router.post("/delete")
def post_delete(data: GroupDeleteRequest):
    """删除分组（spec 010）。

    两种模式：

    * ``delete_tasks=False``（默认）：组内任务退回未分组，任务本身不删。
    * ``delete_tasks=True``：连组内任务一起彻底删除（DB 行 + 结果/状态/转写等派生
      文件），与 ``/delete_task_record`` 共用 ``services/task_cleanup.py`` 这一份实现。

    **进行中的任务一律跳过**并退回未分组：删掉正在跑的任务只会留下一个继续占着
    下载与转写资源、谁也看不见的孤儿（见 ``services/task_cleanup.py`` 的说明）。
    跳过的条目随 ``skipped_tasks`` 返回，让前端能如实告诉用户「有几条没删、为什么」。
    """
    try:
        deleted_tasks: list = []
        skipped_tasks: list = []
        if data.delete_tasks:
            from app.db.note_group_dao import list_task_ids_in_group
            from app.services.task_cleanup import (
                TaskInFlightError,
                delete_task_completely,
            )

            for task_id in list_task_ids_in_group(data.group_id):
                try:
                    delete_task_completely(task_id)
                    deleted_tasks.append(task_id)
                except TaskInFlightError as exc:
                    skipped_tasks.append({"task_id": task_id, "reason": str(exc)})
                except Exception as exc:
                    logger.warning("删除分组内任务 %s 失败：%s", task_id, exc)
                    skipped_tasks.append({"task_id": task_id, "reason": str(exc)})

        # 刻意放在删任务之后：这样 affected 正好是「退回未分组」的条数（= 跳过的那些）。
        affected = delete_group(data.group_id)
        return R.success(
            {
                "affected": affected,
                "deleted_tasks": deleted_tasks,
                "skipped_tasks": skipped_tasks,
            }
        )
    except NoteGroupError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("删除笔记分组失败")
        return R.error(f"删除笔记分组失败：{exc}", code=500)


@router.post("/assign")
def post_assign(data: TaskGroupRequest):
    """把单个任务移进/移出分组（前端拖拽）。"""
    try:
        assign_task_to_group(data.task_id, _normalize_group_id(data.group_id))
        return R.success(
            {"task_id": data.task_id, "group_id": _normalize_group_id(data.group_id)}
        )
    except NoteGroupError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("移动任务到分组失败")
        return R.error(f"移动任务到分组失败：{exc}", code=500)


@router.post("/assign_batch")
def post_assign_batch(data: TasksGroupRequest):
    """批量移入/移出分组。"""
    try:
        affected = assign_tasks_to_group(
            data.task_ids, _normalize_group_id(data.group_id)
        )
        return R.success({"affected": affected})
    except NoteGroupError as exc:
        return R.error(str(exc), code=400)
    except Exception as exc:
        logger.exception("批量移动任务到分组失败")
        return R.error(f"批量移动任务到分组失败：{exc}", code=500)


@router.get("/tasks")
def get_group_tasks(group_id: Optional[str] = None):
    """列出某个分组（不传 = 未分组）里的全部 task_id。"""
    try:
        from app.db.note_group_dao import list_task_ids_in_group

        task_ids = list_task_ids_in_group(_normalize_group_id(group_id))
        return R.success({"task_ids": task_ids, "total": len(task_ids)})
    except Exception as exc:
        logger.exception("列出分组内任务失败")
        return R.error(f"列出分组内任务失败：{exc}", code=500)


def _batch_task_ids(raw: Any) -> list:
    """把批量请求里的 task_ids 清洗成去重的 id 列表。"""
    seen: Dict[str, None] = {}
    for item in raw or []:
        text = str(item or "").strip()
        if text:
            seen.setdefault(text, None)
    return list(seen.keys())
