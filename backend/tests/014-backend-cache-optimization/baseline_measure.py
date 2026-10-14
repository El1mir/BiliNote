"""工单 01：基线测量 —— 后端缓存优化的 before 数字。

为什么是独立脚本而不是 pytest 用例：
本文件只负责**打点**（生成数字 + 落盘 JSON），断言留给后续的实现 ticket。
把它写成脚本，是为了让缓存实现前后能用同一条命令、同一批数据各跑一次，
直接把两份 JSON 对比，而不必让测试同时承担「测量」与「门禁」两个职责。

怎么用（在 backend/ 目录下）：

    .\\.venv\\Scripts\\python.exe tests\\014-backend-cache-optimization\\baseline_measure.py
    .\\.venv\\Scripts\\python.exe tests\\014-backend-cache-optimization\\baseline_measure.py --tasks 200 --repeat 5

输出：``baseline-result.json``（同目录），以及 stdout 上的人类可读表格。

隔离原则：**绝不碰用户的真实库与真实数据目录**。
* 任务行写进 tmp 目录下的独立 SQLite；
* 状态文件/结果文件写进 tmp 目录，靠 ``NOTE_OUTPUT_DIR`` 环境变量指过去。

测量手段：用 ``sys.settrace`` 以外的轻量办法 —— 给内建 ``open`` / ``os.stat``
打计数器（monkeypatch 模块级符号 + 包装内建）。之所以不用 cProfile：我们要的
是「发生了多少次系统调用」，不是「每个函数花了多少 CPU 时间」。
"""

from __future__ import annotations

import argparse
import builtins
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import orjson

# --- 让脚本能 import app.*（backend/ 是包根） ---------------------------------
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


# ===========================================================================
# 计数器：内建 open / os.stat（读盘放大就是靠这两个看出来的）
# ===========================================================================


class Counters:
    """全局系统调用计数器。测量期间只加不清，取差值用 :meth:`reset`。"""

    def __init__(self) -> None:
        self.open_calls = 0
        self.stat_calls = 0
        self.bytes_read = 0

    def reset(self) -> None:
        self.open_calls = 0
        self.stat_calls = 0
        self.bytes_read = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "open_calls": self.open_calls,
            "stat_calls": self.stat_calls,
            "bytes_read": self.bytes_read,
        }


COUNTERS = Counters()

_real_open = builtins.open
_real_stat = os.stat
_real_is_file = Path.is_file
_real_read_text = Path.read_text

#: C 实现会绕过 ``builtins.open`` 的路径前缀 —— 对这些路径的 open 计数会偏少，
#: 必须用 stat 计数交叉验证。这是**计数器自身的已知盲区**，不是被测代码的属性。
_CPP_IMPL_PREFIXES = (
    os.path.join(str(_BACKEND_DIR), "app"),
    os.path.join(str(_BACKEND_DIR), "events"),
)


def _counting_open(file, mode="r", *args, **kwargs):
    """包装内建 open。

    只统计**读**模式里真正读到的字节数：写模式记 open 次数但不算 bytes_read，
    否则会把状态写入的流量混进「读放大」这个指标里。
    """
    target = file
    if isinstance(target, int):
        # 已经是文件描述符，没有路径可查，直接放行不计 open。
        return _real_open(file, mode, *args, **kwargs)

    if isinstance(target, (str, os.PathLike)):
        path_str = os.fspath(target)
        resolved = os.path.abspath(path_str)
        if not resolved.startswith(_CPP_IMPL_PREFIXES):
            COUNTERS.open_calls += 1
            if "r" in mode and "+" not in mode:
                try:
                    st = _real_stat(resolved)
                    COUNTERS.bytes_read += st.st_size
                except OSError:
                    pass
    else:
        # IOBase / bytes 之类，open 都不接受（会 TypeError）；交给真 open 去报错。
        pass

    return _real_open(file, mode, *args, **kwargs)


def _counting_stat(*args, **kwargs):
    COUNTERS.stat_calls += 1
    return _real_stat(*args, **kwargs)


def _counting_is_file(self):
    COUNTERS.stat_calls += 1
    return _real_is_file(self)


def _counting_read_text(self, encoding=None, errors=None):
    COUNTERS.open_calls += 1
    try:
        COUNTERS.bytes_read += _real_stat(self).st_size
    except OSError:
        pass
    return _real_read_text(self, encoding=encoding, errors=errors)


def install_counters() -> None:
    builtins.open = _counting_open
    os.stat = _counting_stat
    # pathlib 的 is_file/read_text 走 C 实现，既不经过 builtins.open 也不经过
    # os.stat（见本模块 docstring 的说明）。这两处显式补上，才能看到
    # ``_task_title_from_file`` / ``_task_has_note`` 的真实读盘量。
    Path.is_file = _counting_is_file  # type: ignore[method-assign]
    Path.read_text = _counting_read_text  # type: ignore[method-assign]
    # os.path.exists 在 posixpath/ntpath 里运行时查 os.stat 模块属性，
    # 所以上面 os.stat 的替换足以让 exists 也计入 stat_calls。


def remove_counters() -> None:
    builtins.open = _real_open
    os.stat = _real_stat
    Path.is_file = _real_is_file
    Path.read_text = _real_read_text


# ===========================================================================
# 造数据
# ===========================================================================


def _fake_status_payload(task_id: str, status: str, progress: int) -> dict:
    """与 ``NoteGenerator._update_status`` 落盘的结构保持一致（含 indent=2）。"""
    return {
        "status": status,
        "stage": "transcribing",
        "stage_label": "转写中",
        "progress": progress,
        "stage_progress": progress,
        "message": f"任务 {task_id} 正在处理",
        "updated_at": "2026-10-14T20:00:00",
        "task_id": task_id,
    }


def _fake_result_payload(task_id: str, index: int) -> dict:
    """结果 JSON：结构上接近真实产物（markdown 有实际体积，标题在 audio_meta）。"""
    return {
        "markdown": f"# 视频 {index} 的笔记\n\n" + ("正文段落内容。" * 400),
        "transcript": {"language": "zh", "segments": []},
        "audio_meta": {"title": f"测试视频标题 {index}", "duration": 600},
    }


def _seed_timestamp(offset_seconds: int) -> datetime:
    """造一个递增的创建时间，让列表顺序稳定（列表接口按创建时间倒序展示）。"""
    return datetime(2026, 10, 14, 20, 0, 0) + timedelta(seconds=offset_seconds)


def seed_database(db_path: Path, task_ids: list[str], platform: str = "bilibili") -> None:
    """把任务行写进独立 SQLite（不碰用户库）。"""
    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}")
    # 先让模型建表：直接 import 模型模块，Base.metadata 上就有了 video_tasks / note_groups
    from app.db.engine import Base  # noqa: F401
    import app.db.models.video_tasks  # noqa: F401
    import app.db.models.note_groups  # noqa: F401

    Base.metadata.create_all(engine)

    # 用 SQLAlchemy Core 的 table 对象拼 INSERT：列名是常量、值是绑定参数，
    # 不经过字符串拼接，天然对注入安全（静态检查也不用去猜 text() 里的内容）。
    from app.db.models.video_tasks import VideoTask

    statement = VideoTask.__table__.insert()
    payload = [
        {
            "video_id": f"BV{i:06d}",
            "platform": platform,
            "task_id": tid,
            "group_id": None,
            # created_at 是 DateTime 列，SQLite 方言只接受 datetime/date 对象，
            # 传字符串会 TypeError（见 sqlalchemy/dialects/sqlite/base.py 的 process）。
            "created_at": _seed_timestamp(i),
        }
        for i, tid in enumerate(task_ids)
    ]
    if not payload:
        engine.dispose()
        return

    with engine.begin() as conn:
        # 逐行 INSERT：statement 由 SQLAlchemy Core 直接从 VideoTask 表对象生成
        # （列名是对象属性、值是绑定变量，全程没有字符串拼接），构造点是常量，
        # 参数来自本函数入参。几百次插入，测量场景无所谓。
        #
        # 性能考虑：这是一次性造数，不进热路径；逐行插入换来的确定性，
        # 比 executemany 的微小速度收益更值。
        for row in payload:
            _insert_row(conn, statement, row)
    engine.dispose()


def _insert_row(conn, statement, row: dict) -> None:
    """把建表语句与参数分开传 —— 参数化 Core 语句，无字符串拼接。

    抽成独立函数是为了让「SQL 从哪来」这一点在静态检查面前显式可见：
    调用方传入的是 VideoTask.__table__.insert() 构造出来的对象，不是字符串。

    静态检查器会对任何把变量喂给 ``execute`` 的地方报警，这里补一行显式忽略：
    语句全部由 SQLAlchemy Core 从表对象生成（列名是对象属性），值全部走绑定变量，
    代码里不存在任何 SQL 字符串拼接，因此该告警在此处是误报。
    """
    conn.execute(statement, row)  # noqa: S608  # nosec B608


def seed_status_files(out_dir: Path, task_ids: list[str], with_result_ratio: float = 0.5) -> None:
    """造状态文件；按比例再补结果文件（模拟「一部分已完成、一部分在跑」）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(task_ids)
    for i, tid in enumerate(task_ids):
        done = i < int(total * with_result_ratio)
        status = "SUCCESS" if done else "TRANSCRIBING"
        progress = 100 if done else (i % 90)
        path = out_dir / f"{tid}.status.json"
        path.write_text(
            json.dumps(_fake_status_payload(tid, status, progress), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if done:
            (out_dir / f"{tid}.json").write_text(
                json.dumps(_fake_result_payload(tid, i), ensure_ascii=False),
                encoding="utf-8",
            )


# ===========================================================================
# 测量项 1：批量轮询 POST /task_status/batch
# ===========================================================================


def measure_batch_poll(client, task_ids: list[str], repeat: int, cache_on: bool) -> dict:
    """每轮 = 一次 POST /api/task_status/batch（前端 3 秒一轮的那个请求）。

    **冷启动与稳态分开报**，这是 ticket 02 之后才需要的区分：

    - ``cold_*``：注册表为空时的第一轮（进程刚起、或某任务第一次被轮询）。
      缓存帮不上忙，它记录的是「最坏一轮」的真实成本。
    - 顶层 ``p50/p95/stat_per_round``：**稳态**，即全部 task_id 都已预热后的轮询。
      这才是前端 99% 时间看到的数字。

    不做这个区分的话，``repeat`` 轮里唯一的冷轮会把平均值冲淡，读起来像是
    「优化只生效了一部分」——而实际上第一轮之后就没有系统调用了。
    """
    timings: list[float] = []
    per_round: list[dict[str, int]] = []

    # 预热一轮：FastAPI 首次请求要编译 pydantic 模型、建路由，别让它污染 p50
    client.post("/api/task_status/batch", json={"task_ids": task_ids[:1]})

    # 冷启动一轮：清空注册表，测「什么都没缓存时」的完整成本。
    if cache_on:
        from app.services import task_status_cache

        task_status_cache.clear()
    COUNTERS.reset()
    cold_t0 = time.perf_counter()
    cold_resp = client.post("/api/task_status/batch", json={"task_ids": task_ids})
    cold_elapsed = time.perf_counter() - cold_t0
    assert cold_resp.status_code == 200, cold_resp.text
    cold_stats = COUNTERS.snapshot()

    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        resp = client.post("/api/task_status/batch", json={"task_ids": task_ids})
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        timings.append(elapsed)
        per_round.append(COUNTERS.snapshot())

    return {
        "task_count": len(task_ids),
        "rounds": repeat,
        "cache": "on" if cache_on else "off",
        "p50_ms": round(statistics.median(timings) * 1000, 2),
        "p95_ms": round(_percentile(timings, 0.95) * 1000, 2),
        "min_ms": round(min(timings) * 1000, 2),
        "max_ms": round(max(timings) * 1000, 2),
        "open_calls_per_round": _avg([r["open_calls"] for r in per_round]),
        "stat_calls_per_round": _avg([r["stat_calls"] for r in per_round]),
        "bytes_read_per_round": _avg([r["bytes_read"] for r in per_round]),
        "cold_ms": round(cold_elapsed * 1000, 2),
        "cold_open_calls": cold_stats["open_calls"],
        "cold_stat_calls": cold_stats["stat_calls"],
    }


def measure_single_status(client, task_ids: list[str], repeat: int) -> dict:
    """单任务详情端点（详情页那条路径，每轮只查一个）。"""
    timings = []
    per_round = []
    target = task_ids[0]
    client.get(f"/api/task_status/{target}")
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        resp = client.get(f"/api/task_status/{target}")
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        timings.append(elapsed)
        per_round.append(COUNTERS.snapshot())
    return {
        "p50_ms": round(statistics.median(timings) * 1000, 2),
        "open_calls_per_call": _avg([r["open_calls"] for r in per_round]),
        "stat_calls_per_call": _avg([r["stat_calls"] for r in per_round]),
    }


# ===========================================================================
# 测量项 2：GET /task_list
# ===========================================================================


def measure_task_list(client, repeat: int) -> dict:
    timings = []
    per_round = []
    client.get("/api/task_list")
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        resp = client.get("/api/task_list")
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        timings.append(elapsed)
        per_round.append(COUNTERS.snapshot())
    return {
        "p50_ms": round(statistics.median(timings) * 1000, 2),
        "p95_ms": round(_percentile(timings, 0.95) * 1000, 2),
        "open_calls_per_call": _avg([r["open_calls"] for r in per_round]),
        "stat_calls_per_call": _avg([r["stat_calls"] for r in per_round]),
        "bytes_read_per_call": _avg([r["bytes_read"] for r in per_round]),
    }


# ===========================================================================
# 测量项 3：只读端点
# ===========================================================================


def measure_endpoint(client, path: str, repeat: int) -> dict:
    timings = []
    per_round = []
    first = client.get(path)
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        # 只关心这次调用的耗时与计数增量；响应体在首次调用时已校验过 status_code。
        client.get(path)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        per_round.append(COUNTERS.snapshot())
    return {
        "status_code": first.status_code,
        "p50_ms": round(statistics.median(timings) * 1000, 2),
        "p95_ms": round(_percentile(timings, 0.95) * 1000, 2),
        "open_calls_per_call": _avg([r["open_calls"] for r in per_round]),
        "stat_calls_per_call": _avg([r["stat_calls"] for r in per_round]),
        "ok": first.status_code == 200,
    }


def measure_transcriber_models_status(client, repeat: int) -> dict:
    """``/transcriber_models_status`` 的冷 / 热两态（ticket 05）。

    这是本 spec 唯一加了 TTL 缓存的只读端点，所以「一次调用多慢」这个口径不够用 ——
    命中与未命中是两回事，必须分开报：

    * ``cold``：每次计时前先清掉扫描缓存（等价于 TTL 到期，也等价于**改动前**的行为）；
    * ``warm``：连续正常调用（命中 5s 槽）。

    改动前的基线**永远**是 cold 态 —— 那时根本没有槽。
    """
    from app.routers import config as config_module

    def _round() -> dict:
        COUNTERS.reset()
        t0 = time.perf_counter()
        resp = client.get("/api/transcriber_models_status")
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        return {"ms": elapsed, "counters": COUNTERS.snapshot()}

    cold = []
    for _ in range(repeat):
        config_module._invalidate_models_status_cache()
        cold.append(_round())

    client.get("/api/transcriber_models_status")  # 预热，保证下面全是命中
    warm = [_round() for _ in range(repeat)]

    def _summarize(rounds) -> dict:
        timings = [r["ms"] for r in rounds]
        return {
            "p50_ms": round(statistics.median(timings) * 1000, 2),
            "p95_ms": round(_percentile(timings, 0.95) * 1000, 2),
            "open_calls_per_call": _avg([r["counters"]["open_calls"] for r in rounds]),
            "stat_calls_per_call": _avg([r["counters"]["stat_calls"] for r in rounds]),
        }

    return {"cold": _summarize(cold), "warm": _summarize(warm)}


# ===========================================================================
# 测量项 4：状态写入（_update_status）
# ===========================================================================


def measure_status_write(out_dir: Path, task_id: str, repeat: int) -> dict:
    """直接调 ``NoteGenerator()._update_status`` —— 单次写入的真实成本。

    这条路径不经过 HTTP，因为它由后台线程直接调用（截图逐张回报就是走这里）。
    """
    from app.services.note import NoteGenerator
    from app.enmus.task_status_enums import TaskStatus

    gen = NoteGenerator()
    gen._update_status(task_id, TaskStatus.TRANSCRIBING)  # 预热

    timings = []
    per_round = []
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        gen._update_status(task_id, TaskStatus.TRANSCRIBING, message="测量中", progress=42)
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)
        per_round.append(COUNTERS.snapshot())

    return {
        "p50_ms": round(statistics.median(timings) * 1000, 2),
        "p95_ms": round(_percentile(timings, 0.95) * 1000, 2),
        "open_calls_per_write": _avg([r["open_calls"] for r in per_round]),
        "stat_calls_per_write": _avg([r["stat_calls"] for r in per_round]),
        "bytes_written_per_write": _status_file_size(out_dir, task_id),
    }


def _status_file_size(out_dir: Path, task_id: str) -> int:
    path = out_dir / f"{task_id}.status.json"
    try:
        return path.stat().st_size
    except OSError:
        return 0


# ===========================================================================
# 测量项 5：纯函数级 —— _read_task_status 与 _task_title_from_file 的开销
# ===========================================================================


def measure_task_list_breakdown(rows_count: int, out_dir: Path, task_ids: list[str], repeat: int) -> dict:
    """把 /task_list 拆成「全表查询」与「每行 2 次文件读」两块，各自计时。

    为什么单独测：ticket 决定「给 /task_list 加缓存」还是「把每行的两次读合并成
    一次批量读」时，需要知道这两块各占多少 —— 如果文件读占九成，缓存只是掩盖
    问题，合并读才是根治。
    """
    from app.db.video_task_dao import list_video_tasks
    from app.routers.note import (
        _read_result_summary,
        _task_has_note,
        _task_title_from_file,
    )

    # 循环外先取一次行数：repeat 可能是 0，循环体内的 rows 会「可能未绑定」。
    rows: list[dict] = list_video_tasks()
    row_count = len(rows)

    sql_times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        rows = list_video_tasks()
        sql_times.append(time.perf_counter() - t0)

    file_times = []
    open_counts = []
    old_stat_counts = []
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        for tid in task_ids:
            _task_title_from_file(tid)
            _task_has_note(tid)
        file_times.append(time.perf_counter() - t0)
        snapshot = COUNTERS.snapshot()
        open_counts.append(snapshot["open_calls"])
        old_stat_counts.append(snapshot["stat_calls"])

    # ticket 04 之后的形态：每行一次 _read_result_summary（一次读盘出两个字段）。
    # 两个数放在一起，才能说清「合并两读」到底省了多少 —— 这是 ticket 04 前后对比的
    # 主判据。
    merged_times = []
    merged_stat_counts = []
    for _ in range(repeat):
        COUNTERS.reset()
        t0 = time.perf_counter()
        for tid in task_ids:
            _read_result_summary(tid)
        merged_times.append(time.perf_counter() - t0)
        merged_stat_counts.append(COUNTERS.snapshot()["stat_calls"])

    return {
        "rows": row_count,
        "sql_only_p50_ms": round(statistics.median(sql_times) * 1000, 2),
        "per_row_file_reads_p50_ms": round(statistics.median(file_times) * 1000, 2),
        "open_calls_per_row": round(_avg(open_counts) / max(1, len(task_ids)), 2),
        "stat_calls_per_row": round(
            _avg(old_stat_counts) / max(1, len(task_ids)), 2
        ),
        "merged_read_p50_ms": round(statistics.median(merged_times) * 1000, 2),
        "merged_stat_calls_per_row": round(
            _avg(merged_stat_counts) / max(1, len(task_ids)), 2
        ),
    }


# ===========================================================================
# 测量项 6：orjson vs 标准库 json（ticket 04 的第二个收益来源）
# ===========================================================================

#: 真实结果文件目录。**刻意用真实数据**而不是测试里造的样例：体积分布才是判断
#: orjson 值不值得的依据（实测 873 个共 47.6MB、平均 55.9KB、中位 18.1KB）。
_REAL_RESULTS_DIR = _BACKEND_DIR / "note_results"


def measure_orjson_benefit(limit: int, repeat: int) -> dict:
    """同一批结果文件分别用标准库 ``json`` 与 ``orjson`` 解析，给出倍数。

    为什么单独测：``/task_list`` 这次改了两件事 —— 把每行的两次读**合并成一次**、
    把**解析器**换成 ``orjson``。报告里必须能说清各自贡献了多少，所以这里只比
    「解析同一份 bytes」，不含任何读盘。

    比法：标准库那边用 ``str``（旧代码是 ``read_text`` 拿到的 str），``orjson`` 那边
    用 ``bytes``（它吃 bytes，我们新代码也是 ``read_bytes``）—— 各自的真实形态。
    """
    if not _REAL_RESULTS_DIR.is_dir():
        return {"available": False, "reason": f"目录不存在：{_REAL_RESULTS_DIR}"}
    paths = sorted(p for p in _REAL_RESULTS_DIR.glob("*.json") if p.is_file())[:limit]
    if not paths:
        return {"available": False, "reason": f"目录里没有结果文件：{_REAL_RESULTS_DIR}"}

    blobs = [path.read_bytes() for path in paths]
    texts = [blob.decode("utf-8") for blob in blobs]
    sizes = sorted(len(blob) for blob in blobs)

    json_times = []
    orjson_times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        for text in texts:
            json.loads(text)
        json_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        for blob in blobs:
            orjson.loads(blob)
        orjson_times.append(time.perf_counter() - t0)

    json_p50 = statistics.median(json_times) * 1000
    orjson_p50 = statistics.median(orjson_times) * 1000
    return {
        "available": True,
        "source_dir": str(_REAL_RESULTS_DIR),
        "file_count": len(blobs),
        "total_bytes": sum(sizes),
        "median_file_bytes": sizes[len(sizes) // 2],
        "json_p50_ms": round(json_p50, 2),
        "orjson_p50_ms": round(orjson_p50, 2),
        "speedup": round(json_p50 / orjson_p50, 2) if orjson_p50 else None,
    }


# ===========================================================================
# 工具
# ===========================================================================


def _avg(values: list[int] | list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return ordered[idx]


def _make_client():
    """FastAPI TestClient（走完整 ASGI 栈，含中间件），不是直调函数。"""
    from fastapi.testclient import TestClient

    import main as main_module

    return TestClient(main_module.app)


# ===========================================================================
# 主流程
# ===========================================================================


def _reset_app_modules() -> None:
    """把 ``backend`` 下的应用模块从 ``sys.modules`` 里清干净，让下一次 import
    重新读取刚设好的环境变量（``NOTE_OUTPUT_DIR`` / ``DATABASE_URL`` /
    ``BILINOTE_CACHE``）。

    ⚠️ 顶层包 ``app`` **本身**也必须删掉。只删 ``app.*`` 子模块是不够的：
    ``app/__init__.py`` 里的 ``create_app`` 靠的是它自己 globals 里那份
    ``app.routers.note`` 引用，包对象不重建的话，``create_app`` 会拿**旧**
    子模块去建路由 —— 于是测的还是上一次的 ``NOTE_OUTPUT_DIR``（默认
    ``note_results``，即仓库里那份真实数据），缓存也就永远不会命中。
    这个坑真的踩过：探针里一度出现「同一个 note.py 文件存在两份模块对象」，
    端点的 ``fn.__globals__`` 与 ``sys.modules["app.routers.note"]`` 不是同一个
    dict，``NOTE_OUTPUT_DIR`` 停留在默认值。
    """
    import importlib

    stale = [
        name
        for name in list(sys.modules)
        if name == "main"
        or name == "app"
        or name.startswith("app.")
        or name in ("events", "ffmpeg_helper")
    ]
    for name in stale:
        del sys.modules[name]
    importlib.invalidate_caches()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="BiliNote 后端缓存基线测量")
    p.add_argument("--tasks", type=int, default=200, help="造多少条任务（默认 200）")
    p.add_argument("--repeat", type=int, default=5, help="每项重复几轮（默认 5）")
    p.add_argument("--also-1000", action="store_true", help="额外跑一次 1000 条任务的规模")
    p.add_argument(
        "--cache",
        choices=["on", "off", "both"],
        default="on",
        help="BILINOTE_CACHE 取值；both = 同一规模跑两遍用于前后对比（默认 on）",
    )
    p.add_argument("--out", type=str, default="", help="结果 JSON 输出路径")
    p.add_argument(
        "--orjson-files",
        type=int,
        default=200,
        help="orjson 微基准用多少个真实结果文件（默认 200，取文件名排序前 N 个）",
    )
    return p


def run_one_scale(
    task_count: int, repeat: int, tmp_root: Path, cache_on: bool = True
) -> dict:
    """在给定规模下跑完所有测量项，返回该规模的结果 dict。"""
    scale_dir = tmp_root / f"n{task_count}" / ("cache-on" if cache_on else "cache-off")
    out_dir = scale_dir / "note_results"
    db_path = scale_dir / "bili_note.db"
    scale_dir.mkdir(parents=True, exist_ok=True)

    task_ids = [f"task-{i:06d}-0000-0000-0000-000000000000" for i in range(task_count)]

    seed_database(db_path, task_ids)
    seed_status_files(out_dir, task_ids)

    # NOTE_OUTPUT_DIR 必须在 import app.routers.note **之前**设好 —— 那个模块在
    # 导入时就把它读成了模块级常量（note.py:131）。
    os.environ["NOTE_OUTPUT_DIR"] = str(out_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    # task_status_cache.disabled() 是每次读环境变量的，所以设在这里就能生效。
    if cache_on:
        os.environ.pop("BILINOTE_CACHE", None)
    else:
        os.environ["BILINOTE_CACHE"] = "off"

    # 清掉可能已被导入的模块，确保它们重新读取上面的环境变量。
    _reset_app_modules()

    from app.db.engine import get_engine

    get_engine().dispose()

    client = _make_client()
    with client:
        result = {
            "task_count": task_count,
            "repeat": repeat,
            "cache": "on" if cache_on else "off",
            "batch_poll": measure_batch_poll(client, task_ids, repeat, cache_on),
            "single_status": measure_single_status(client, task_ids, repeat),
            "task_list": measure_task_list(client, repeat),
            "task_list_breakdown": measure_task_list_breakdown(
                task_count, out_dir, task_ids, repeat
            ),
            "readonly_endpoints": {
                path: measure_endpoint(client, path, repeat)
                for path in (
                    "/api/sys_health",
                    "/api/deploy_status",
                    "/api/transcriber_models_status",
                    "/api/transcriber_config",
                )
            },
            "transcriber_models_status": measure_transcriber_models_status(client, repeat),
            "status_write": measure_status_write(out_dir, task_ids[-1], repeat),
        }

    get_engine().dispose()
    return result


def main() -> int:
    args = build_parser().parse_args()

    tmp_root = Path(tempfile.mkdtemp(prefix="bili-baseline-"))
    install_counters()
    all_results = []
    try:
        scales = [args.tasks]
        if args.also_1000 and 1000 not in scales:
            scales.append(1000)
        cache_modes = {"on": [True], "off": [False], "both": [False, True]}[args.cache]
        for n in scales:
            for cache_on in cache_modes:
                label = "缓存开" if cache_on else "缓存关"
                print(f"\n=== 规模 N={n} / {label} ===", flush=True)
                res = run_one_scale(n, args.repeat, tmp_root, cache_on)
                all_results.append(res)
                _print_scale(res)
    finally:
        remove_counters()
        shutil.rmtree(tmp_root, ignore_errors=True)

    # orjson 微基准与规模、缓存开关都无关，只跑一次。
    orjson_benefit = measure_orjson_benefit(args.orjson_files, args.repeat)
    _print_orjson(orjson_benefit)

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parent / "baseline-result.json"

    # 防误覆盖：默认输出文件里若已存在**不同规模 / 不同 repeat / 不同缓存开关**的
    # 结果，先备份再写。基线是后续所有前后对比的基准，一次不小心的 `--tasks 20`
    # 快跑就会把它冲掉（本 ticket 实施期间真的发生过一次；该文件未被 git 跟踪、
    # 无从恢复，只能重跑）。签名里带上 cache 是因为 on/off 两组必须同时留存：
    # 只留一组就等于把对比的另一半删了。
    if out_path.exists():
        try:
            old_results = json.loads(out_path.read_text(encoding="utf-8")).get("results") or []
        except (OSError, ValueError):
            old_results = []
        new_sig = [
            (r.get("task_count"), r.get("repeat"), r.get("cache")) for r in all_results
        ]
        old_sig = [
            (r.get("task_count"), r.get("repeat"), r.get("cache")) for r in old_results
        ]
        if old_sig and old_sig != new_sig:
            backup = out_path.with_name(f"{out_path.stem}.backup-{_now().replace(':', '')}.json")
            shutil.copy2(out_path, backup)
            print(f"\n[!] 覆盖了不同规模的旧结果，已备份到：{backup}")

    out_path.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "orjson_benefit": orjson_benefit,
                "results": all_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n结果已写入：{out_path}")
    return 0


def _now() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _print_scale(res: dict) -> None:
    bp = res["batch_poll"]
    print(
        f"  批量轮询 {bp['task_count']} 条（缓存 {bp['cache']}）: "
        f"稳态 p50={bp['p50_ms']}ms p95={bp['p95_ms']}ms "
        f"| open/轮={bp['open_calls_per_round']} stat/轮={bp['stat_calls_per_round']} "
        f"读入/轮={bp['bytes_read_per_round']}B"
    )
    print(
        f"    └ 冷启动一轮（注册表为空）: {bp['cold_ms']}ms "
        f"open={bp['cold_open_calls']} stat={bp['cold_stat_calls']}"
    )
    tl = res["task_list"]
    bd = res["task_list_breakdown"]
    print(
        f"  GET /task_list: p50={tl['p50_ms']}ms open/次={tl['open_calls_per_call']} "
        f"| 其中 SQL={bd['sql_only_p50_ms']}ms "
        f"({bd['open_calls_per_row']} open/行)"
    )
    print(
        f"    └ 每行文件读：改动前两次读={bd['per_row_file_reads_p50_ms']}ms "
        f"→ 合并后一次读={bd['merged_read_p50_ms']}ms "
        f"| stat/行 {bd['stat_calls_per_row']} → {bd['merged_stat_calls_per_row']}"
    )
    for path, m in res["readonly_endpoints"].items():
        print(f"  {path}: p50={m['p50_ms']}ms open/次={m['open_calls_per_call']} ok={m['ok']}")
    ms = res["transcriber_models_status"]
    print(
        f"  /transcriber_models_status 冷/热: "
        f"cold p50={ms['cold']['p50_ms']}ms stat/次={ms['cold']['stat_calls_per_call']} "
        f"→ warm p50={ms['warm']['p50_ms']}ms stat/次={ms['warm']['stat_calls_per_call']}"
    )
    sw = res["status_write"]
    print(
        f"  _update_status: p50={sw['p50_ms']}ms open/次={sw['open_calls_per_write']} "
        f"文件={sw['bytes_written_per_write']}B"
    )


def _print_orjson(benefit: dict) -> None:
    if not benefit.get("available"):
        print(f"\n  orjson 微基准：跳过（{benefit.get('reason')}）")
        return
    megabytes = benefit["total_bytes"] / 1024 / 1024
    print(
        f"\n  orjson 微基准（真实结果文件 {benefit['file_count']} 个 / {megabytes:.1f}MB，"
        f"中位 {benefit['median_file_bytes']}B）: "
        f"json={benefit['json_p50_ms']}ms orjson={benefit['orjson_p50_ms']}ms "
        f"→ {benefit['speedup']}×"
    )


if __name__ == "__main__":
    raise SystemExit(main())
