# app/services/task_retry.py
"""失败任务的原地重试（spec 011）。

## 为什么需要它

任务失败后就只剩「重新走一遍生成表单」这一条路 —— 用户得重新找到那个视频、重新
选一次参数。批量导入 200 条时挂了 30 条，等于要手工重来 30 次。这个模块提供
「把失败的任务原地再跑一遍」的能力。

## 「重试」在这里是什么意思

**复用同一个 task_id 与分组归属**，把 ``payload_json`` 里创建时存下的参数原样取出、
重新入队。任务列表里那条记录从「失败」变回「排队中」，历史不会因为一次重试而多出
一条重复记录。

这与 ``services/task_recovery.py``（服务重启后恢复在途任务）共用同一套「从 DB 行还原
``run_note_task`` 参数」的逻辑，但**判定方向相反**：

* 启动恢复只碰**在途**任务，故意不碰 FAILED（「FAILED 是已经有结论的任务，重启后
  自己活过来会让用户莫名其妙」）。
* 本模块**只碰 FAILED**，而且必须由用户显式发起 —— 用户要的就是让那个「有结论的
  失败」再试一次。

## 参数从哪来

``payload_json`` 列。老库的行没有这一列、或写入时序列化失败时，按 ``video_id``
重建一个最小可用参数集（只对 bilibili 能重建 URL）；重建不了的行**跳过并告知原因**，
而不是拿默认参数硬跑 —— 那会生成一篇参数完全不对的笔记。

## 什么任务不重试

* **SUCCESS**：已经有笔记了，重跑只会覆盖掉用户已经看过的东西。想再生成一次应该
  走正常提交入口（那边有「已生成」去重提示）。
* **在途**（PENDING/PARSING/…/SAVING）：它还在跑，重试等于把同一个 task_id 跑两遍，
  两个线程写同一份文件。
* **状态文件读不到**：不知道它是什么状态，不猜（与启动恢复不同 —— 那边读不到恰恰
  最该恢复，因为进程在写第一次状态前就被杀了；这里进程活得好好的，读不到只说明
  这个任务从没真正开始过，重试它没有依据）。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

#: 只有这个状态可重试。
FAILED_STATUS = "FAILED"

#: 在途状态 —— 明确排除，避免同一个 task_id 被同时跑两遍。
#: 与 ``routers/note.py`` 和 ``services/task_recovery.py`` 保持一致。
IN_FLIGHT_STATUSES = frozenset(
    {
        "PENDING",
        "PARSING",
        "DOWNLOADING",
        "TRANSCRIBING",
        "SUMMARIZING",
        "FORMATTING",
        "SAVING",
    }
)

#: 能从 payload_json 还原给 ``run_note_task`` 的键。
#: 与 ``services/task_recovery.py`` 的 ``_PAYLOAD_KEYS`` 是同一份契约
#: （也就是 ``routers/note.py`` 的 ``_build_task_kwargs`` 那 19 个键去掉 task_id）。
PAYLOAD_KEYS = (
    "video_url",
    "platform",
    "quality",
    "link",
    "screenshot",
    "_format",
    "scene",
    "detail",
    "extras",
    "video_understanding",
    "video_interval",
    "grid_size",
    "sampling_mode",
    "max_frames",
    "frames_per_second",
    "frame_limit_mode",
    "ocr_assist",
    "group_id",
)


def _note_output_dir() -> str:
    """结果目录的唯一来源。

    延迟 import ``app.routers.note`` 而不是自己 ``os.getenv``：测试用
    ``monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp)`` 覆盖它，自己再读一份
    环境变量会让 monkeypatch 管不到本模块（``services/task_cleanup.py`` 的
    ``_output_dir`` 有同样的注释与理由）。
    """
    from app.routers import note as note_router

    return note_router.NOTE_OUTPUT_DIR


def read_task_status(task_id: str) -> Optional[str]:
    """读 ``<task_id>.status.json`` 的 status；文件不存在/损坏/无该键返回 ``None``。"""
    path = os.path.join(_note_output_dir(), f"{task_id}.status.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.debug("读取任务状态文件失败（%s）：%s", task_id, exc)
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    return str(status) if status else None


def read_task_failure_message(task_id: str) -> str:
    """读失败任务的错误消息（给用户看「为什么失败」，重试前先判断值不值得）。"""
    path = os.path.join(_note_output_dir(), f"{task_id}.status.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    return str(message) if message else ""


def _fallback_payload(video_id: str, platform: str) -> Optional[dict]:
    """``payload_json`` 缺失时按 ``video_id`` 重建最小参数集（只支持 bilibili）。

    与 ``services/task_recovery.py`` 的同名函数职责一致。这里不做「跨模块复用」是
    刻意的：两个模块的降级策略会各自演化（恢复要尽量救活，重试要尽量不误导），
    强行共用一个函数反而会让任意一边改不动。
    """
    if not video_id or platform != "bilibili":
        return None
    bvid = video_id
    page = 1
    if "_p" in video_id:
        head, _, tail = video_id.rpartition("_p")
        # tail 来自用户视频号。用 try/except 而不是 `isdigit()` 前置守卫：这条规则是
        # 纯语法启发式（不认 `isdigit()` 这类守卫），而「解析失败就退回第 1 集」本来
        # 也就是它该有的行为。
        try:
            parsed = int(tail)
        except ValueError:
            parsed = 0
        # 全零/负数这类极端输入仍要挡掉，否则会拼出 ?p=0 这种无效地址。
        if parsed > 0:
            bvid, page = head, parsed
    if not bvid.startswith("BV"):
        return None
    url = f"https://www.bilibili.com/video/{bvid}"
    if page > 1:
        url = f"{url}?p={page}"
    return {"video_url": url, "platform": platform}


def payload_from_row(row: dict) -> Optional[dict]:
    """从任务行还原 ``run_note_task`` 的参数；还原不了返回 ``None``。"""
    task_id = row.get("task_id")
    raw = row.get("payload_json")
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            logger.warning(
                "任务 %s 的 payload_json 解析失败，尝试按 video_id 重建：%s", task_id, exc
            )
            parsed = None
        if isinstance(parsed, dict):
            payload = {key: parsed[key] for key in PAYLOAD_KEYS if key in parsed}
            if payload.get("video_url"):
                # task_id / platform 以数据库为准，不让 payload 里的旧值覆盖。
                payload["task_id"] = task_id
                payload["platform"] = payload.get("platform") or row.get("platform")
                return payload

    fallback = _fallback_payload(
        str(row.get("video_id") or ""), str(row.get("platform") or "")
    )
    if not fallback:
        return None
    fallback["task_id"] = task_id
    fallback["group_id"] = row.get("group_id")
    return fallback


def _as_row_dict(row: Any) -> Optional[dict]:
    """把 DAO 返回的行统一成 dict —— 两条取数路径的类型并不一致。

    ``list_recoverable_tasks()`` 返回 dict，``get_video_task()`` 返回 **ORM 对象**，
    而本模块的 ``_select_retryable`` / ``payload_from_row`` 一律按 dict 访问
    （``row.get(...)``）。不统一就会在真实故障里炸掉整个重试请求：

        AttributeError: 'VideoTask' object has no attribute 'get'

    ``scope="all"`` 恰好走的是返回 dict 的 DAO，所以这个 bug 只在按分组重试时暴露 ——
    用户点「重试失败任务」看到的是「重试失败」，一条任务都没重排。
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    from app.db.video_task_dao import _row_to_dict

    return _row_to_dict(row)


def _select_retryable(rows: List[dict]) -> tuple[List[dict], List[Dict[str, Any]]]:
    """挑出可重试的失败任务，并给出被跳过项的原因（按传入顺序）。

    返回 ``(retryable_rows, skipped)``；``skipped`` 每条是
    ``{"task_id", "reason"}`` —— 界面上要如实告诉用户「有几条没重试、为什么」，
    静默跳过等于让用户以为全都重试了。
    """
    retryable: List[dict] = []
    skipped: List[Dict[str, Any]] = []
    for row in rows:
        task_id = str(row.get("task_id") or "")
        if not task_id:
            continue
        status = read_task_status(task_id)
        if status == FAILED_STATUS:
            retryable.append(row)
        elif status in IN_FLIGHT_STATUSES:
            skipped.append({"task_id": task_id, "reason": "任务仍在执行"})
        elif status is None:
            skipped.append({"task_id": task_id, "reason": "任务尚未开始，没有可重试的失败记录"})
        else:
            # SUCCESS，以及任何将来新增的未知状态：不猜。
            skipped.append({"task_id": task_id, "reason": f"任务状态为 {status}，无需重试"})
    return retryable, skipped


def retry_failed_tasks(task_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """把失败的任务重新入队；返回统计信息（也在测试里断言用）。

    :param task_ids: 要重试的 task_id 列表；``None`` = 库里全部任务（由调用方按
        分组范围先过滤好）。**以数据库为准**：传进来的 id 必须真的存在于
        ``video_tasks`` 表里，否则无从还原参数。
    :return: ``{"candidates", "requeued", "skipped", "missing"}``。
        ``requeued`` 是成功重新入队的 task_id 列表；``skipped`` 是
        ``{"task_id", "reason"}``；``missing`` 是库里查不到的 id。

    这个函数**同步**跑完扫描与入队，但入队本身只是往分发池丢引用（非阻塞），
    所以它不会等待任务跑完。
    """
    # 延迟导入：路由层 import 服务层的东西很多，模块级 import 容易成环；
    # 而且这些模块（含 NoteGenerator 链）会让启动变慢。
    from app.db.video_task_dao import get_video_task, list_recoverable_tasks
    from app.enmus.task_status_enums import TaskStatus
    from app.routers.note import _dispatch_note_task
    from app.services.note import NoteGenerator

    wanted = None
    if task_ids is not None:
        # 去重但保持顺序：重复提交同一个 id 会让同一个任务被入队两次。
        wanted = list(dict.fromkeys(str(t).strip() for t in task_ids if str(t).strip()))

    missing: List[str] = []
    if wanted is None:
        # 全部任务：与启动恢复走同一个 DAO（它按 created_at 升序返回全部行）。
        rows = list_recoverable_tasks()
    else:
        # 逐个查库而不是拉全表再过滤：分组范围也可能几百条，但用户看得见的那几十条
        # 才是常态。查不到的 id 记进 missing 如实汇报 —— 那说明这条任务在别处已被
        # 删除，重试它无从还原参数。
        rows = []
        for task_id in wanted:
            row = _as_row_dict(get_video_task(task_id))
            if row is None:
                missing.append(task_id)
            else:
                rows.append(row)

    stats: Dict[str, Any] = {
        "candidates": len(rows),
        "requeued": [],
        "skipped": [],
        "missing": missing,
    }

    retryable, skipped = _select_retryable(rows)
    stats["skipped"] = skipped

    for row in retryable:
        task_id = str(row.get("task_id") or "")
        payload = payload_from_row(row)
        if not payload:
            stats["skipped"].append(
                {
                    "task_id": task_id,
                    "reason": "缺少可用的生成参数（创建时未存参数，且无法按视频号重建）",
                }
            )
            continue

        try:
            NoteGenerator()._update_status(
                task_id,
                TaskStatus.PENDING,
                message="用户手动重试",
            )
        except Exception as exc:
            logger.warning("重试：写回 PENDING 失败（%s）：%s", task_id, exc)

        # _dispatch_note_task 只认 run_note_task 的关键字参数，payload 里多出来的
        # 键会 TypeError；按 PAYLOAD_KEYS 白名单重建，并显式补上 task_id。
        task_kwargs: Dict[str, Any] = {"task_id": task_id}
        for key in PAYLOAD_KEYS:
            if key in payload:
                task_kwargs[key] = payload[key]
        task_kwargs["video_url"] = payload["video_url"]
        task_kwargs["platform"] = (
            payload.get("platform") or row.get("platform") or "bilibili"
        )
        try:
            _dispatch_note_task(task_kwargs)
            stats["requeued"].append(task_id)
        except Exception as exc:
            logger.error("重试：重新入队失败（%s）：%s", task_id, exc)
            stats["skipped"].append({"task_id": task_id, "reason": f"重新入队失败：{exc}"})

    logger.info(
        "失败任务重试：候选 %d 条，重新入队 %d 条，跳过 %d 条，库中不存在 %d 条",
        stats["candidates"],
        len(stats["requeued"]),
        len(stats["skipped"]),
        len(stats["missing"]),
    )
    return stats
