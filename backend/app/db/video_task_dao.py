from typing import Optional

from app.db.models.video_tasks import VideoTask
from app.db.engine import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


# 插入任务
def insert_video_task(
    video_id: str,
    platform: str,
    task_id: str,
    group_id: Optional[str] = None,
    payload_json: Optional[str] = None,
):
    """写入一条任务记录；``group_id`` 为空表示未分组。

    任务行在**入队时**就写（见 routers/note.py），所以这里必须能带上归属 ——
    否则用户新建的批量任务要等生成完才出现在对应分组里，中间那几分钟列表是空的。

    ``payload_json`` 是提交时的完整生成参数 JSON（spec 009 决策 8–10）。存下来
    是为了让进程重启后能把中断的在途任务按**原参数**重新入队；不传时写 NULL，
    恢复逻辑会回落到默认参数。
    """
    db = next(get_db())
    try:
        task = VideoTask(
            video_id=video_id,
            platform=platform,
            task_id=task_id,
            group_id=group_id,
            payload_json=payload_json,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        logger.info(
            f"Video task inserted successfully. video_id: {video_id}, platform: {platform}, task_id: {task_id}"
        )
    except Exception as e:
        logger.error(f"Failed to insert video task: {e}")
    finally:
        db.close()


def get_video_task(task_id: str):
    """按 task_id 取一条任务记录（没有则 None）。"""
    db = next(get_db())
    try:
        return db.query(VideoTask).filter_by(task_id=task_id).first()
    except Exception as e:
        logger.error(f"Failed to get video task: {e}")
        return None
    finally:
        db.close()


# 查询任务（最新一条）
def get_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        task = (
            db.query(VideoTask)
            .filter_by(video_id=video_id, platform=platform)
            .order_by(VideoTask.created_at.desc())
            .first()
        )
        if task:
            # 去重探测是高频调用（批量展开时每个分P一次），命中/未命中都只在 debug 记
            logger.debug(
                f"Task found for video_id: {video_id} and platform: {platform}"
            )
            return task.task_id
        else:
            logger.debug(
                f"No task found for video_id: {video_id} and platform: {platform}"
            )
            return None
    except Exception as e:
        logger.error(f"Failed to get task by video: {e}")
    finally:
        db.close()


def list_video_tasks():
    """列出全部任务记录，最新的排在前面。

    任务列表整个迁到后端是用户决策 m04951（前端不再本地持久化），前端刷新后
    就是靠这个接口重建列表。返回普通 dict 而不是 ORM 实例：调用方（路由层）
    会直接把它们塞进 JSON 响应，ORM 实例一旦离开 session 就会触发 DetachedInstanceError。

    ``payload_json`` 也一并带出（spec 009 决策 8–10），供启动恢复读取；它是新增
    key，原有 key 一个没动，既有调用方不受影响。注意本函数**没有 LIMIT**：任务
    攒到几千行时每次都是全表读 + 全量序列化，所以「只读在途任务」的启动恢复
    走下面那个专门函数，别拿这个当恢复入口。

    :return: 每条任务一个 dict，含 ``task_id`` / ``video_id`` / ``platform`` /
        ``group_id`` / ``payload_json`` / ``created_at``；读库失败返回空列表。
    """
    db = next(get_db())
    try:
        rows = (
            db.query(VideoTask)
            .order_by(VideoTask.created_at.desc(), VideoTask.id.desc())
            .all()
        )
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to list video tasks: {e}")
        return []
    finally:
        db.close()


def _row_to_dict(row: VideoTask) -> dict:
    """把 ORM 行摊平成普通 dict（含 payload_json）。

    统一在这里摊平，避免 list_video_tasks 与 list_recoverable_tasks 各写一份、
    将来加字段时漏掉一个。
    """
    return {
        "task_id": row.task_id,
        "video_id": row.video_id,
        "platform": row.platform,
        "group_id": row.group_id,
        "payload_json": row.payload_json,
        "created_at": row.created_at,
    }


def list_recoverable_tasks() -> list[dict]:
    """列出全部任务行，供**启动恢复**扫描在途任务用（spec 009 决策 8–10）。

    为什么这里不接一个 ``statuses`` 参数、直接在 SQL 里按状态过滤：任务状态
    **不在数据库里**。``video_tasks`` 只有 video_id/platform/task_id/group_id/
    payload_json/created_at，真正的 status 写在 ``<task_id>.status.json`` 文件里
    （见 routers/note.py 的 ``_get_task_record``）。在 DAO 层按状态过滤就必须
    去读那些状态文件，等于把文件布局耦合进数据访问层；更糟的是**读不到的**行
    （状态文件还没生成）会被静默丢掉 —— 那恰恰是最需要恢复的一批（进程在写状态
    文件之前就被杀）。所以这里返回全部行，由调用方按状态文件决定谁该重入队，
    读不到状态文件的行按「需要恢复」处理。

    :return: 每条任务一个 dict（形状同 ``list_video_tasks``，含 ``payload_json``）；
        调用方用 ``json.loads(payload_json)`` 还原提交时的生成参数，解析失败或为
        NULL 时回落到默认参数。读库失败返回空列表（启动恢复不该拦住启动）。
    """
    db = next(get_db())
    try:
        rows = (
            db.query(VideoTask)
            .order_by(VideoTask.created_at.asc(), VideoTask.id.asc())
            .all()
        )
        return [_row_to_dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Failed to list recoverable video tasks: {e}")
        return []
    finally:
        db.close()


# 删除任务
def delete_video_task(task_id: str) -> int:
    """按 task_id 删除任务记录，返回实际删掉的行数。

    ``/delete_task`` 那个老接口是空壳（只有 TODO），前端删掉本地那条之后一刷新
    又冒出来 —— 因为任务列表现在整个来自后端。
    """
    db = next(get_db())
    try:
        deleted = db.query(VideoTask).filter_by(task_id=task_id).delete()
        db.commit()
        logger.info(f"Video task deleted. task_id: {task_id}, rows: {deleted}")
        return int(deleted or 0)
    except Exception as e:
        logger.error(f"Failed to delete video task: {e}")
        return 0
    finally:
        db.close()


# 删除任务（按视频）
def delete_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        tasks = (
            db.query(VideoTask).filter_by(video_id=video_id, platform=platform).all()
        )
        for task in tasks:
            db.delete(task)
        db.commit()
        logger.info(
            f"Task(s) deleted for video_id: {video_id} and platform: {platform}"
        )
    except Exception as e:
        logger.error(f"Failed to delete task by video: {e}")
    finally:
        db.close()
