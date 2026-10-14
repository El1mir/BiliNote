# app/services/task_cleanup.py
"""任务的彻底删除（spec 010）。

「删掉一个任务」这件事以前只有一份实现，内联在 ``routers/note.py`` 的
``delete_task_record`` 里。spec 010 要求「删除分组时可以连组内笔记一起删」，如果
那时再抄一份，就会出现两份会各自漂移的「什么算删干净」—— ``utils/video_reader.py``
的 Windows ``os.rename`` 缺陷正是这么来的。所以这里收敛成唯一实现，路由层只负责
参数校验与响应包装。

**进行中守卫**：任务被删后 DB 行与 ``.status.json`` 都没了，但工作线程还在跑，
它会重新写出结果文件、继续占着下载与转写资源，变成一个谁也看不见的孤儿。
``is_task_in_flight`` 用「运行登记表 + 状态文件」两个信号判定，取舍见该函数的文档串。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.video_task_dao import delete_video_task
from app.enmus.task_status_enums import TaskStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 任务产物在结果目录下的派生文件后缀，对应 ``<task_id><suffix>``。
TASK_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    ".json",
    ".status.json",
    "_transcript.json",
    "_audio.json",
    ".gpt.checkpoint.json",
)

#: 终态。与 ``services/task_recovery.py`` 的 ``_FINISHED_STATUSES`` 保持一致。
FINISHED_STATUSES = frozenset({TaskStatus.SUCCESS.value, TaskStatus.FAILED.value})


#: 本进程正在执行、以及**已排队待执行**的 task_id。
#:
#: 为什么需要它：``_enqueue_task`` 只写 DB 行、不写状态文件，而 ``generate()`` 真正
#: 开始干活的第一件事才是写 PARSING（``services/note.py:277``）。200 条批量里有
#: 190 多条长期停在「已进池、还没轮到」这个状态 —— 只看状态文件完全看不见它们。
_RUNNING_TASKS: set = set()
_RUNNING_LOCK = threading.Lock()


def mark_task_running(task_id: Optional[str]) -> None:
    """登记一个任务为「进行中」。

    必须在**提交到执行池那一刻**调用，而不是等工作线程真正开始跑：否则「已排队但
    还没轮到」的任务会被误判成可删。
    """
    text = str(task_id or "").strip()
    if not text:
        return
    with _RUNNING_LOCK:
        _RUNNING_TASKS.add(text)


def unmark_task_running(task_id: Optional[str]) -> None:
    """注销运行登记。任务的 ``finally`` 里必须调用，否则它会永远删不掉。"""
    text = str(task_id or "").strip()
    if not text:
        return
    with _RUNNING_LOCK:
        _RUNNING_TASKS.discard(text)


def is_task_running(task_id: Optional[str]) -> bool:
    """该 task_id 是否登记在册（本进程视角）。"""
    text = str(task_id or "").strip()
    if not text:
        return False
    with _RUNNING_LOCK:
        return text in _RUNNING_TASKS


def running_task_ids() -> frozenset:
    """当前登记为进行中的 task_id 快照（测试与诊断用）。"""
    with _RUNNING_LOCK:
        return frozenset(_RUNNING_TASKS)


def clear_running_tasks() -> None:
    """清空登记表。**仅供测试**：进程级状态不该跨用例泄漏。"""
    with _RUNNING_LOCK:
        _RUNNING_TASKS.clear()


class TaskInFlightError(Exception):
    """任务仍在执行，拒绝删除。"""


def _output_dir() -> Path:
    """结果目录的唯一来源。

    延迟 import ``app.routers.note``：那边在模块级读环境变量，测试用
    ``monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp)`` 覆盖它。如果在这里
    再 ``os.getenv`` 一份，测试的 monkeypatch 就管不到本模块，删除会打到真实目录
    —— ``IMAGE_OUTPUT_DIR`` 之前正是这么把测试产物写进仓库的。

    模块级 import 会造成循环依赖（``routers/note.py`` 要 import 本模块），所以放在
    函数里；``routers/note.py`` 只在真正调用删除时才会被拉起来。
    """
    from app.routers import note as note_router

    return Path(note_router.NOTE_OUTPUT_DIR)


def read_task_status(task_id: str) -> Optional[str]:
    """读 ``<task_id>.status.json`` 的 status；文件不存在或损坏返回 ``None``。"""
    path = _output_dir() / f"{task_id}.status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status else None


def is_task_in_flight(task_id: str) -> bool:
    """任务是否仍在执行。两个信号任一命中即算进行中。

    1. **本进程的运行登记表**（``mark_task_running`` / ``unmark_task_running``）：
       任务被丢进执行池时登记，跑完或异常退出时注销。这是唯一能覆盖「已排队但还没
       开始跑」的信号，而那恰恰是 200 条批量里最长期的状态。
    2. **状态文件**：存在 ``.status.json`` 且状态不是 SUCCESS/FAILED。

    刻意**不用**「DB 行存在」兜底：容量边界会把 ``note_output`` 整个纳入清理候选
    （``services/media_resource_service.py:743-770``），状态文件可能先于 DB 行消失。
    那种任务在列表里显示成「等待中」，若被判成进行中就会永远删不掉、前端也没有别的
    出口。有了运行登记表，就不再需要这个粗糙且会造成死路的兜底。
    """
    if is_task_running(task_id):
        return True
    status = read_task_status(task_id)
    if status is None:
        return False
    return status not in FINISHED_STATUSES


def _delete_artifacts(task_id: str) -> List[str]:
    """删掉结果目录下该任务的派生文件，返回删掉的文件名。"""
    base = _output_dir()
    deleted: List[str] = []
    for suffix in TASK_ARTIFACT_SUFFIXES:
        path = base / f"{task_id}{suffix}"
        try:
            if path.is_file():
                path.unlink()
                deleted.append(path.name)
        except Exception as exc:
            # 单个文件删不掉不该让整次删除失败：DB 行已经没了，任务不会再出现在列表里。
            logger.warning("删除任务文件失败（%s）：%s", path.name, exc)
    return deleted


def delete_task_completely(
    task_id: str, *, allow_in_flight: bool = False
) -> Dict[str, Any]:
    """删掉一个任务的 DB 记录与全部派生文件。

    返回 ``{"task_id", "removed", "files"}``；``removed`` 是删掉的 DB 行数
    （``0`` = 本来就没有这条记录，不算失败）。

    ``allow_in_flight=False``（默认）时任务仍在执行会抛 :class:`TaskInFlightError`。
    """
    text = str(task_id or "").strip()
    if not text:
        raise ValueError("task_id 不能为空")
    if not allow_in_flight and is_task_in_flight(text):
        raise TaskInFlightError("任务仍在执行，请等它结束或失败后再删除")

    removed = delete_video_task(text)
    files = _delete_artifacts(text)
    # 内存注册表必须同步失效（spec 014 ticket 02/03）：否则删掉的任务会被
    # ``_read_task_status`` 继续命中内存里的旧状态返回给前端 —— 症状正是
    # 前端删掉一条、列表刷新后它又冒出来。放在删文件之后是刻意的：
    # 先删投影再删内存，任何中途崩溃都只会退化成「多读一次文件」，
    # 不会留下「内存已清但文件还在」这种读者能看见的窗口。
    try:
        from app.services import task_status_cache

        task_status_cache.drop(text)
    except Exception:
        logger.exception("删除任务后清理内存状态失败（%s）", text)
    logger.info("彻底删除任务 %s：DB 行 %d，文件 %s", text, removed, files or "无")
    return {"task_id": text, "removed": removed, "files": files}
