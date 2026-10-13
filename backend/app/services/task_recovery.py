"""启动恢复：把上次进程被杀时仍在途的任务重新排进执行队列（spec 009 ticket 03）。

## 为什么需要它

任务队列是**纯内存**的：批量提交后任务只存在于 ``ThreadPoolExecutor`` 的队列和
线程里，进程一退（重启、OOM、用户关掉终端）就全没了。而任务行已经在数据库里，
状态文件写着 ``PENDING``/``DOWNLOADING``/…，于是界面上这些任务永远停在「排队中」
—— 它们排队等一个已经死掉的队列。

## 恢复什么、不恢复什么（用户决策 m00231 / m00235）

* **只恢复在途状态**（PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/
  FORMATTING/SAVING），或者**状态文件读不到**的行 —— 后者恰恰最该恢复：进程在
  写完第一次状态之前就被杀了。
* **FAILED 不动**。FAILED 是已经有结论的任务（重试也失败了），重启后自己活过来
  会让用户莫名其妙。用户想重跑就自己重新提交。
* **SUCCESS 不动**。

## 参数从哪来

``payload_json`` 列（ticket 03 新增）。老库的行没有这一列，或者写入时序列化失败，
这时按 ``video_id`` 重建一个最小可用的参数集（只对 bilibili 能重建 URL）；重建不了
的行**跳过并记日志**，而不是拿默认参数硬跑 —— 那会生成一篇参数完全不对的笔记。

## 幂等与不阻塞

* 恢复是幂等的：同一批行重复扫描只会重复入队，而 ``_is_task_in_flight`` 那套
  去重是按 ``(video_id, platform)`` 走的，恢复入口自己也查一遍状态，避免重复。
* 扫描在**独立线程**里跑（``_recover_in_background``），启动序列不等它 ——
  数据库里有几百行 + 逐个读状态文件不该拖慢后端起来的时间。
"""

import json
import os
import threading

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 与 routers/note.py 的 _IN_FLIGHT_STATUSES 一致（这里是本地副本，避免
# 服务层 import 路由层造成循环依赖；两边任意一边改了都要同步）。
_IN_FLIGHT_STATUSES = frozenset(
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

_FINISHED_STATUSES = frozenset({"SUCCESS", "FAILED"})

# 恢复时只认这些 payload 键；其余（未知字段）忽略，避免把脏数据塞给 run_note_task。
_PAYLOAD_KEYS = (
    "video_url",
    "platform",
    "quality",
    "link",
    "screenshot",
    "_format",
    "style",
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
    return os.getenv("NOTE_OUTPUT_DIR", "note_results")


def _read_status(task_id: str) -> "str | None":
    """读 ``<task_id>.status.json`` 的 status；文件不存在/读不了/没这个键返回 None。

    返回 None 的含义是「不知道状态」—— 调用方把它当作**需要恢复**处理，
    因为最常见的成因就是进程在写第一次状态之前就被杀了。
    """
    path = os.path.join(_note_output_dir(), f"{task_id}.status.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("status")
    except Exception as exc:
        logger.debug("读取任务状态文件失败（%s）：%s", task_id, exc)
        return None


def _fallback_payload(video_id: str, platform: str) -> "dict | None":
    """payload_json 缺失时，用 video_id 重建一个最小参数集。

    只对 bilibili 能重建 URL（``BV1xx`` 或 ``BV1xx_p2`` 形式）。其它平台没有
    原始链接就无法下载，返回 None —— 调用方会跳过这一条并记日志。

    参数值全部走默认：这是「尽力而为」的恢复，宁可跑出默认参数的笔记，也不能
    因为它缺参数就永远卡在「排队中」。
    """
    if not video_id or platform != "bilibili":
        return None
    bvid = video_id
    page = 1
    if "_p" in video_id:
        head, _, tail = video_id.rpartition("_p")
        if tail.isdigit():
            bvid, page = head, int(tail)
    if not bvid.startswith("BV"):
        return None
    url = f"https://www.bilibili.com/video/{bvid}"
    if page > 1:
        url = f"{url}?p={page}"
    return {"video_url": url, "platform": platform}


def _payload_from_row(row: dict) -> "dict | None":
    """从任务行还原 ``run_note_task`` 的参数；还原不了返回 None。"""
    raw = row.get("payload_json")
    if raw:
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            logger.warning(
                "任务 %s 的 payload_json 解析失败，尝试按 video_id 重建：%s",
                row.get("task_id"),
                exc,
            )
            parsed = None
        if isinstance(parsed, dict):
            payload = {k: parsed[k] for k in _PAYLOAD_KEYS if k in parsed}
            if payload.get("video_url"):
                # task_id / video_id 以数据库为准，不让 payload 里的旧值覆盖。
                payload["task_id"] = row.get("task_id")
                payload["platform"] = payload.get("platform") or row.get("platform")
                return payload

    fallback = _fallback_payload(
        str(row.get("video_id") or ""), str(row.get("platform") or "")
    )
    if not fallback:
        return None
    fallback["task_id"] = row.get("task_id")
    return fallback


def _select_recoverable(rows: "list[dict]") -> "list[dict]":
    """从全部任务行里挑出该恢复的（在途 / 状态未知），保持传入顺序。"""
    selected = []
    for row in rows:
        task_id = str(row.get("task_id") or "")
        if not task_id:
            continue
        status = _read_status(task_id)
        if status in _FINISHED_STATUSES:
            continue
        if status is not None and status not in _IN_FLIGHT_STATUSES:
            # 未知状态（新版本加的状态？）：不猜，跳过并留痕。
            logger.warning(
                "任务 %s 状态为 %s，不在已知集合内，跳过恢复", task_id, status
            )
            continue
        selected.append(row)
    return selected


def recover_interrupted_tasks() -> dict:
    """扫描并重新入队在途任务；返回统计信息（也在测试里断言用）。

    这个函数**同步**执行完扫描与入队，但入队本身只是往分发池丢引用（非阻塞），
    所以它不会等待任务跑完。生产入口是 :func:`_recover_in_background`。
    """
    stats = {"scanned": 0, "requeued": 0, "skipped_finished": 0, "skipped_invalid": 0}

    # 延迟导入：路由层 import 服务层的东西很多，模块级 import 容易成环；
    # 而且这些模块（含 NoteGenerator 链）会让启动变慢，没必要在 import 期拉起。
    from app.db.video_task_dao import list_recoverable_tasks
    from app.routers.note import (
        _dispatch_note_task,
        _get_circuit_breaker,
    )
    from app.services.note import NoteGenerator
    from app.enmus.task_status_enums import TaskStatus

    rows = list_recoverable_tasks()
    stats["scanned"] = len(rows)

    for row in rows:
        status = _read_status(str(row.get("task_id") or ""))
        if status in _FINISHED_STATUSES:
            stats["skipped_finished"] += 1

    recoverable = _select_recoverable(rows)
    if not recoverable:
        logger.info("启动恢复：没有需要在途任务（扫描 %d 条）", stats["scanned"])
        return stats

    # 熔断开关是关的就别恢复了：连续失败已达阈值，再把几百条重新排进去
    # 等于绕过熔断（用户明确说过重新提交才复位）。
    if _get_circuit_breaker().is_paused():
        logger.warning("启动恢复：连续失败熔断处于暂停状态，本次不恢复任何任务")
        return stats

    for row in recoverable:
        task_id = str(row.get("task_id") or "")
        payload = _payload_from_row(row)
        if not payload:
            stats["skipped_invalid"] += 1
            logger.warning(
                "启动恢复：任务 %s 缺少可用参数（payload_json 为空且无法按 video_id 重建），跳过",
                task_id,
            )
            continue

        try:
            NoteGenerator()._update_status(
                task_id,
                TaskStatus.PENDING,
                message="服务重启后自动恢复",
            )
        except Exception as exc:
            logger.warning("启动恢复：写回 PENDING 失败（%s）：%s", task_id, exc)

        # _dispatch_note_task 只认 run_note_task 的关键字参数，payload 里多出来的
        # 键会 TypeError；所以这里按 _PAYLOAD_KEYS 白名单重建，并显式补上 task_id。
        task_kwargs = {"task_id": task_id}
        for key in _PAYLOAD_KEYS:
            if key in payload:
                task_kwargs[key] = payload[key]
        task_kwargs["video_url"] = payload["video_url"]
        task_kwargs["platform"] = (
            payload.get("platform") or row.get("platform") or "bilibili"
        )
        try:
            _dispatch_note_task(task_kwargs)
            stats["requeued"] += 1
        except Exception as exc:
            logger.error("启动恢复：重新入队失败（%s）：%s", task_id, exc)

    logger.info(
        "启动恢复完成：扫描 %d 条，重新入队 %d 条，"
        "已完成跳过 %d 条，参数不可用跳过 %d 条",
        stats["scanned"],
        stats["requeued"],
        stats["skipped_finished"],
        stats["skipped_invalid"],
    )
    return stats


def _recover_in_background() -> None:
    """在独立线程里跑恢复，绝不阻塞启动序列。"""
    try:
        recover_interrupted_tasks()
    except Exception:
        # 恢复失败只是「这次重启没救回任务」，不该让后端起不来。
        logger.exception("启动恢复异常（不影响后端启动）")


def start_recovery_thread() -> threading.Thread:
    """启动恢复线程并返回它（测试可以直接 join）。

    用 daemon=True：恢复没跑完时进程退出不该被它拖住。
    """
    thread = threading.Thread(
        target=_recover_in_background,
        name="task-recovery",
        daemon=True,
    )
    thread.start()
    return thread
