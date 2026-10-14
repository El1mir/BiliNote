"""任务状态的进程内内存注册表（轮询快路径）。

为什么需要它
------------
前端每 3 秒用 ``POST /task_status/batch`` 拉一次全部任务状态
（``BillNote_frontend/src/hooks/useTaskPolling.ts:53``）。原先每次轮询都要对
**每个** task_id 走一遍 ``os.path.exists`` + ``open`` + ``json.load``
（``app/routers/note.py`` 的 ``_read_task_status``）。N=200 时实测
**198.46ms / 轮、899.8 次 stat / 轮**，且与任务是否在推进无关——已经跑完的任务
状态文件一个字节都没变，却每 3 秒被重新 stat 一次。

真正的危害不是 IO 量，而是**同步系统调用阻塞事件循环**：后端是单进程 uvicorn
（``main.py`` 的 ``uvicorn.run(..., reload=False)``），这 200 次同步 stat 会把
下载 / 转写 / LLM 请求一起堵在后面。基线单条 ``GET /task_status/{id}`` 是
``p50=1.62ms / stat=6.0 / open=0.0``，说明开销几乎全在 stat 上。

为什么这么小
------------
轮询读的是 ``.status.json``，实测**平均 216 字节**（219 个文件，最大 231B），
且批量端点传 ``include_result=False``，成功任务**不会**去读 56KB 的结果文件。
所以这里不需要指纹校验、不需要 TTL、不需要代际号——那些机械是为「重解析大文件」
设计的。本模块只做一件事：**按 task_id 存 dict**。约 30 行，够用。

（需要重解析大文件的地方是 ``GET /task_list``，它每行把同一份 55.9KB 的结果文件
读两遍；那个场景由 ticket 04 用 ``orjson`` 处理，不走这里。）

为什么不用锁
------------
写入方**不唯一**，这一点是实测出来的、与最初的设计假设相反：截图阶段有 8 个
``screenshot_*`` 线程会并发写同一个 task_id（``services/note.py`` 的
``_insert_screenshots`` / ``_insert_approved_screenshots`` 用
``ThreadPoolExecutor`` 并行渲染，每个 worker 各自回报进度）。此外
``task_recovery.py`` 的恢复线程与 ``task_retry.py`` 的请求线程也会写。

即便如此仍然**不加锁**，因为安全性的来源不是「单写者」，而是**整份替换**：
``_update_status`` 每次都从零构造一个完整 ``data``（``services/note.py:1497``），
从不读-改-写。因此并发的后果只是「最后写的人赢」，任何一方写进去的都是完整状态，
不存在读到半截状态或字段互相污染。GIL 下 dict 的单个 ``__setitem__`` / ``get``
本身即原子，业务层不需要额外锁。

**若日后写入方改成读-改-写（例如只更新某个字段），这个论证立刻失效**，必须补锁——
不能再靠「整份替换」兜底。

进程启动即空，不做落盘恢复——重启后的重建由 ``task_recovery.py`` 从 DB +
``.status.json`` 投影文件完成。这也意味着落盘文件仍然是权威的**持久**副本，
本模块只是它的内存快路径。
"""
import os
from typing import Any, Optional

# task_id -> _read_task_status 产出的轻量 payload
_store: dict[str, dict[str, Any]] = {}

#: 关掉内存快路径的环境变量取值（大小写不敏感）。
_FALSY = {"0", "false", "off", "no"}


def disabled() -> bool:
    """内存快路径是否被 ``BILINOTE_CACHE`` 关掉。

    用途是**前后对比测量**（同一个测量脚本跑「关」与「开」两组数字），不是让生产
    随时关缓存。每次读环境变量而不做缓存：本模块全部代码就 30 行左右，为一个
    几乎不在热路径上的 ``os.environ.get`` 引入模块级状态不值得，而且会让测试里
    的 ``monkeypatch.setenv`` 失效。
    """
    raw = os.environ.get("BILINOTE_CACHE")
    if raw is None:
        return False
    return raw.strip().lower() in _FALSY


def get(task_id: str) -> Optional[dict[str, Any]]:
    """取内存里的任务状态；未命中或快路径被关闭时返回 ``None``。"""
    if disabled():
        return None
    return _store.get(task_id)


def put(task_id: str, payload: dict[str, Any]) -> None:
    """写入任务状态（**权威副本**）。

    调用方约定：``NoteGenerator._update_status`` 先 ``put`` 再落盘。落盘是投影，
    失败只影响「重启后读回」，不影响本次运行的正确性。
    """
    _store[task_id] = payload


def drop(task_id: str) -> None:
    """丢弃某个任务的内存状态。

    每一条**删除或复用 task_id** 的路径都必须调它，否则会把已删除 / 已重跑的旧
    状态继续返回给前端——症状是「删了又冒出来」，``app/routers/note.py`` 里对此
    有过记录。重试是原地复用同一个 task_id，尤其容易漏。
    """
    _store.pop(task_id, None)


def clear() -> None:
    """清空全部内存状态（测试用；也用于模拟进程重启）。"""
    _store.clear()
