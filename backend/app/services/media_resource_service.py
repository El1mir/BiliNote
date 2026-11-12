"""Register and safely clean files inside configured media roots."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.db.engine import SessionLocal
from app.db.models.media_resources import MediaResource
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 容量边界（spec 007 §12 / spec 009 ticket 07）
# ---------------------------------------------------------------------------
# 既有清理只认时间维度（`expires_at <= now`）。长批量任务（200 × 1–3h 的 mp3
# 约 6–18 GB，开截图/视频理解则达数百 GB）在保留期内足以写满磁盘，所以新增
# 一条**容量维度**：已完成任务的本地资源总量超过 `cache_limit_bytes` 就按最旧
# 优先回收，不等过期。

#: 通用设置读不到 / 键还没落地时的兜底值，与 spec 007 §12.2 的默认值一致。
DEFAULT_CACHE_LIMIT_BYTES = 10 * 1024**3
DEFAULT_MIN_FREE_DISK_BYTES = 5 * 1024**3
DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 5

#: 删到上限的这个比例就停手，而不是刚好删到等于上限。
#: 理由：清理器每小时才跑一次（`media_cleanup_loop`）。若每轮都只删到「刚好
#: 等于上限」，下一轮开始时必然又超限 —— 每一轮都真的要删文件，而且字节粒度
#: 上的等号判定极其脆弱。留 10% 余量后，一轮清理能撑住一段时间的新增写入，
#: 清理动作变成间歇的，而不是持续贴着上限删。
_CACHE_LOW_WATER_RATIO = 0.9

#: 任务终态（spec 007 §12.1 决策 13「终态即清」）：只有这两个状态才允许回收
#: 其资源。其余（PENDING/PARSING/DOWNLOADING/TRANSCRIBING/SUMMARIZING/
#: FORMATTING/SAVING）都是「进行中」，资源正在被使用，一律跳过。
#: 这里刻意不 import `app/routers/note.py` 的 `_IN_FLIGHT_STATUSES`：那是路由
#: 模块（会拉起整条 API 依赖），而清理循环只需要一个状态字符串白名单。
_TERMINAL_STATUSES = {"SUCCESS", "FAILED"}

#: `uploads/` 与 `data/note_output/` 里的文件没有 task 归属（`/uploads/<name>`
#: 只是静态路径），无法用状态文件判断是否被活跃任务使用。改用 mtime 宽限：
#: 这段时间内被动过的文件一律不删。代价是磁盘吃紧时最新的上传件暂时回收不了，
#: 收益是「用户刚上传、任务还在排队」的文件不会被清理器抢先删掉。
_UNATTRIBUTED_GRACE_SECONDS = 24 * 3600

#: ASR 切片目录（`asr_chunks_*` / `asr_speech_*`）正被转写中的任务使用，目录
#: mtime 会随切片写入而更新；同样用宽限保护正在跑的长音频转写。
_TEMP_GRACE_SECONDS = 6 * 3600

#: 0 字节文件可能只是「刚被创建、马上要写」的中间态，给一小时宽限。
_ZERO_BYTE_GRACE_SECONDS = 3600

#: `visual_cache` 里 `*.tmp-<uuid>` 是写缓存时的暂存目录（video_reader.py:427），
#: 正常路径会被 rename 成正式条目或清理掉；残留说明进程被打断过。同样给宽限，
#: 避免删掉另一个进程正在写的暂存目录。
_VISUAL_CACHE_TMP_GRACE_SECONDS = 3600

#: 观测报告里最多回显多少条「被跳过」的样本，避免一次扫描产出巨大响应。
_SKIPPED_SAMPLE_LIMIT = 50


def _roots() -> dict[str, Path]:
    from app.utils.path_helper import get_data_dir

    data_root = Path(get_data_dir()).resolve()
    screenshot_root = Path(os.getenv("OUT_DIR", "./static/screenshots"))
    if not screenshot_root.is_absolute():
        screenshot_root = Path(__file__).resolve().parents[2] / screenshot_root
    return {
        "screenshot": screenshot_root.resolve(),
        "video": data_root,
        "audio": data_root,
    }


def _row_value(row, name: str):
    """Read a scalar attribute off an ORM row, typed ``Any``.

    为什么需要：SQLAlchemy 2.x 的声明式属性在静态分析里被推断成
    ``Column[int]`` / ``Column[datetime]``，而不是实例值本身。于是
    ``if row.expires_at``、``min(row.expires_at ...)`` 这类写法会被 pyright
    报 ``reportGeneralTypeIssues`` / ``reportArgumentType``。

    本仓库既有做法是用 ``int()`` / ``str()`` 构造器把值取出来（见
    ``_registered_row_fields`` 与各 DAO 的 ``setattr`` 写法）；这里给
    datetime 之类的场景补一个通用出口 —— 属性名是变量时 ``getattr`` 的结果
    就是 ``Any``，不会再把 Column 类型带进下游。
    """
    return getattr(row, name)


def _mark_row_failed(row, message: str) -> None:
    """把一行标记成删除失败。

    用 ``setattr`` 而不是 ``row.delete_state = ...``：声明式属性在类型层面是
    ``Column[str]``，直接赋值会被 pyright 报 ``reportAttributeAccessIssue``。
    这是本仓库既有写法（见 ``provider_dao.py`` / ``general_settings_dao.py``）。
    """
    setattr(row, "delete_state", "failed")
    setattr(row, "last_error", message[:1000])


def get_retention_settings() -> dict[str, int]:
    from app.db.models.media_settings import MediaSettings

    with SessionLocal() as db:
        # pi-lens-ignore: python-sql-injection
        row = db.query(MediaSettings).filter_by(id=1).one_or_none()
        if row:
            return {
                "screenshot_retention_days": _as_non_negative_int(
                    _row_value(row, "screenshot_retention_days"), 0
                ),
                "media_retention_days": _as_non_negative_int(
                    _row_value(row, "media_retention_days"), 0
                ),
            }
    return {
        "screenshot_retention_days": _as_non_negative_int(
            os.getenv("SCREENSHOT_RETENTION_DAYS"), 7
        ),
        "media_retention_days": _as_non_negative_int(
            os.getenv("MEDIA_RETENTION_DAYS"), 3
        ),
    }


def set_retention_settings(screenshot_days: int, media_days: int) -> dict[str, int]:
    from app.db.models.media_settings import MediaSettings

    if screenshot_days < 0 or media_days < 0:
        raise ValueError("保留天数必须为非负整数")
    with SessionLocal() as db:
        # pi-lens-ignore: python-sql-injection
        row = db.query(MediaSettings).filter_by(id=1).one_or_none()
        if row is None:
            row = MediaSettings(id=1)
            db.add(row)
        setattr(row, "screenshot_retention_days", screenshot_days)
        setattr(row, "media_retention_days", media_days)
        db.commit()
    return {
        "screenshot_retention_days": screenshot_days,
        "media_retention_days": media_days,
    }


def _managed_relative(resource_type: str, file_path: Path) -> str:
    root = _roots()[resource_type]
    # Reject traversal and every symlink component before resolving. Checking only
    # the final path misses an in-root symlinked directory whose target is elsewhere.
    raw = Path(os.path.abspath(file_path))
    try:
        relative = raw.relative_to(root)
    except ValueError as exc:
        raise ValueError("resource path is outside its managed root") from exc
    if any(part in (".", "..") for part in relative.parts):
        raise ValueError("resource path contains traversal")
    cursor = root
    if root.is_symlink():
        raise ValueError("managed root is a symbolic link")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("resource path contains a symbolic link")
    resolved = raw.resolve()
    if resolved == root or root not in resolved.parents or not resolved.is_file():
        raise ValueError("resource path is outside its managed root or is not a file")
    return relative.as_posix()


def register_resource(
    resource_type: str,
    file_path: str | Path,
    task_id: str | None = None,
    video_id: str | None = None,
    created_at: datetime | None = None,
    source: str = "generated",
) -> None:
    if resource_type not in ("screenshot", "video", "audio"):
        raise ValueError("unsupported media resource type")
    path = Path(file_path)
    relative = _managed_relative(resource_type, path)
    created = created_at or datetime.now(timezone.utc).replace(tzinfo=None)
    settings = get_retention_settings()
    days = settings[
        "screenshot_retention_days"
        if resource_type == "screenshot"
        else "media_retention_days"
    ]
    expires = created + timedelta(days=days) if days else None
    key = f"{resource_type}:{relative}"
    with SessionLocal() as db:
        if db.query(MediaResource.id).filter_by(path=key).first():
            return
        db.add(
            MediaResource(
                resource_type=resource_type,
                task_id=task_id,
                video_id=video_id,
                path=key,
                size_bytes=path.stat().st_size,
                created_at=created,
                expires_at=expires,
                source=source,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def _count_path(kind: str, path: Path) -> int:
    with SessionLocal() as db:
        key = f"{kind}:{_managed_relative(kind, path)}"
        return db.query(MediaResource.id).filter_by(path=key).count()


def backfill_legacy_resources() -> int:
    roots = _roots()
    extensions = {
        "screenshot": {".jpg", ".jpeg", ".png", ".webp"},
        "video": {".mp4", ".mkv", ".webm", ".mov"},
        "audio": {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus"},
    }
    inserted = 0
    for kind, root in roots.items():
        if not root.is_dir():
            continue
        try:
            candidates = root.rglob("*") if kind == "screenshot" else root.iterdir()
            for path in candidates:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.suffix.lower() not in extensions[kind]
                ):
                    continue
                try:
                    before = _count_path(kind, path)
                    created = datetime.fromtimestamp(path.stat().st_mtime)
                    register_resource(
                        kind, path, created_at=created, source="legacy_backfill"
                    )
                    inserted += 1 if _count_path(kind, path) > before else 0
                except Exception:
                    logger.exception("Media resource backfill failed for managed file")
        except OSError:
            logger.exception("Media backfill directory scan failed")
    return inserted


def _selected_types(resource_types: list[str] | None) -> list[str]:
    selected = list(dict.fromkeys(resource_types or ["screenshot", "video", "audio"]))
    if not selected or not set(selected) <= {"screenshot", "video", "audio"}:
        raise ValueError("unsupported media resource type")
    return selected


def preview_cleanup(
    resource_types: list[str] | None = None, expired_only: bool = True
) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    selected = _selected_types(resource_types)
    with SessionLocal() as db:
        # pi-lens-ignore: python-sql-injection
        query = db.query(MediaResource).filter(
            MediaResource.resource_type.in_(selected),
            MediaResource.delete_state.in_(["active", "failed"]),
        )
        if expired_only:
            query = query.filter(
                MediaResource.expires_at.isnot(None), MediaResource.expires_at <= now
            )
        rows = query.all()
    expires_values = [
        value
        for value in (_row_value(row, "expires_at") for row in rows)
        if value is not None
    ]
    return {
        "count": len(rows),
        "bytes": sum(
            _as_non_negative_int(_row_value(row, "size_bytes"), 0) for row in rows
        ),
        "by_type": {
            kind: {
                "count": sum(
                    1 for row in rows if _row_value(row, "resource_type") == kind
                ),
                "bytes": sum(
                    _as_non_negative_int(_row_value(row, "size_bytes"), 0)
                    for row in rows
                    if _row_value(row, "resource_type") == kind
                ),
            }
            for kind in selected
        },
        # 转成 ISO 字符串再返回：这两个字段会进 JSON 响应，直接给 datetime 会在
        # 序列化时抛 TypeError: Object of type datetime is not JSON serializable，
        # 表现为「预览全部」返回 500（`get_recent_cleanup_runs` 早已按 ISO 约定输出）。
        "expires_earliest": min(expires_values).isoformat() if expires_values else None,
        "expires_latest": max(expires_values).isoformat() if expires_values else None,
    }


def get_recent_cleanup_runs(limit: int = 10) -> list[dict]:
    from app.db.models.media_cleanup_run import MediaCleanupRun

    with SessionLocal() as db:
        rows = (
            # pi-lens-ignore: python-sql-injection
            db.query(MediaCleanupRun)
            .order_by(MediaCleanupRun.completed_at.desc(), MediaCleanupRun.id.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
        recent: list[dict] = []
        for row in rows:
            completed_at = _row_value(row, "completed_at")
            resource_types = _row_value(row, "resource_types")
            recent.append(
                {
                    "resource_types": str(resource_types or "").split(",")
                    if resource_types
                    else [],
                    "expired_only": _row_value(row, "expired_only"),
                    "deleted": _row_value(row, "deleted"),
                    "missing": _row_value(row, "missing"),
                    "failed": _row_value(row, "failed"),
                    "bytes_freed": _row_value(row, "bytes_freed"),
                    "requested": _row_value(row, "requested"),
                    "completed_at": completed_at.isoformat()
                    if completed_at is not None
                    else None,
                }
            )
        return recent


def cleanup_resources(
    resource_types: list[str] | None = None,
    expired_only: bool = True,
    limit: int = 200,
) -> dict:
    selected = _selected_types(resource_types)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    report = {"deleted": 0, "missing": 0, "failed": 0, "bytes": 0, "requested": 0}
    with SessionLocal() as db:
        # pi-lens-ignore: python-sql-injection
        query = db.query(MediaResource).filter(
            MediaResource.resource_type.in_(selected),
            MediaResource.delete_state.in_(["active", "failed"]),
        )
        if expired_only:
            query = query.filter(
                MediaResource.expires_at.isnot(None), MediaResource.expires_at <= now
            )
        rows = query.order_by(MediaResource.id).limit(max(1, min(limit, 1000))).all()
        report["requested"] = len(rows)
        roots = _roots()
        for row in rows:
            kind, separator, relative = row.path.partition(":")
            root = roots.get(kind)
            if not separator or root is None:
                _mark_row_failed(row, "invalid managed resource key")
                report["failed"] += 1
                continue
            raw_target = root / relative
            try:
                lexical_relative = raw_target.relative_to(root)
                if not lexical_relative.parts or any(
                    part in (".", "..") for part in lexical_relative.parts
                ):
                    raise ValueError("invalid relative path")
                cursor = root
                if root.is_symlink():
                    raise ValueError("managed root is a symbolic link")
                for part in lexical_relative.parts:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        raise ValueError("managed path contains a symbolic link")
            except ValueError:
                _mark_row_failed(
                    row, "managed path escaped root or contains a symbolic link"
                )
                report["failed"] += 1
                continue
            target = raw_target.resolve()
            if target == root or root not in target.parents:
                _mark_row_failed(row, "managed path escaped root")
                report["failed"] += 1
                continue
            try:
                if target.exists():
                    target.unlink()
                    report["deleted"] += 1
                    report["bytes"] += _as_non_negative_int(
                        _row_value(row, "size_bytes"), 0
                    )
                else:
                    report["missing"] += 1
                db.delete(row)
            except OSError as exc:
                _mark_row_failed(row, str(exc))
                report["failed"] += 1
        db.commit()

    logger.info(
        "Media cleanup completed: types=%s expired_only=%s deleted=%s missing=%s failed=%s bytes=%s",
        selected,
        expired_only,
        report["deleted"],
        report["missing"],
        report["failed"],
        report["bytes"],
    )
    try:
        from app.db.models.media_cleanup_run import MediaCleanupRun

        with SessionLocal() as db:
            db.add(
                MediaCleanupRun(
                    resource_types=",".join(selected),
                    expired_only=expired_only,
                    deleted=report["deleted"],
                    missing=report["missing"],
                    failed=report["failed"],
                    bytes_freed=report["bytes"],
                    requested=report["requested"],
                    completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            db.commit()
    except Exception:
        logger.exception("Failed to persist media cleanup audit report")
    return report


# ---------------------------------------------------------------------------
# 容量维度：扫描 / 统计 / 回收
# ---------------------------------------------------------------------------


def _as_non_negative_int(value, default: int) -> int:
    """把设置值转成非负整数；None / 非法 / 负数一律回退到默认值。

    `cache_limit_bytes == 0` 是**合法**值（表示不设上限），所以这里 0 必须原样
    保留，不能当成「空值」被默认值顶掉。
    """
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def get_cache_settings() -> dict[str, int]:
    """读取容量边界相关的通用设置（只读，带兜底）。

    三个键由并行任务在 `general_settings` 里新增。本模块**只读不写**，并且一律
    走 `dict.get(key, default)`：那个任务还没合入时 DAO 返回的字典里根本没有这些
    键，或者整个读取直接抛异常 —— 两种情况都必须回退到 spec 007 §12.2 的默认值。
    清理是尽力而为的后台工作，不能因为读设置失败就停摆，更不能让接口 500。
    """
    raw: dict = {}
    try:
        from app.db.general_settings_dao import get_general_settings

        raw = get_general_settings() or {}
    except Exception:
        logger.warning("读取通用设置失败，容量边界回退到默认值", exc_info=True)
    return {
        "cache_limit_bytes": _as_non_negative_int(
            raw.get("cache_limit_bytes"), DEFAULT_CACHE_LIMIT_BYTES
        ),
        "min_free_disk_bytes": _as_non_negative_int(
            raw.get("min_free_disk_bytes"), DEFAULT_MIN_FREE_DISK_BYTES
        ),
        "circuit_breaker_threshold": _as_non_negative_int(
            raw.get("circuit_breaker_threshold"), DEFAULT_CIRCUIT_BREAKER_THRESHOLD
        ),
    }


def _note_output_dir() -> Path:
    """任务状态文件所在目录。

    与 `app/services/note.py:66` 的 `NOTE_OUTPUT_DIR` 同一语义（环境变量可覆盖，
    默认相对 cwd 的 `note_results`）。刻意不 import 那个模块：它是生成流水线的
    业务服务，import 它会拉起整条 LLM/下载依赖，而清理循环只需要读一个状态文件。
    """
    return Path(os.getenv("NOTE_OUTPUT_DIR", "note_results"))


def _note_export_dir() -> Path:
    """导出产物目录（PDF/DOCX/MD 的落盘位置）。

    与 `app/utils/export.py:13-15` 的 `SAVE_PATH` 同源（`DATA_DIR` 环境变量可
    覆盖，默认 `<backend>/data/note_output`）。同样刻意不 import：那个模块会拉起
    markdown_pdf 等导出依赖。
    """
    from app.utils.path_helper import get_data_dir

    # spec 022 D4：导出目录与下载/媒体登记同根，避免再各自解析 DATA_DIR。
    return (Path(get_data_dir()) / "note_output").resolve()


def _task_status(task_id: str | None, cache: dict[str, str | None]) -> str | None:
    """读 `<NOTE_OUTPUT_DIR>/<task_id>.status.json` 里的 status。

    返回 None 表示「读不到」——状态文件缺失、损坏、或者资源压根没有 task_id。
    调用方必须把 None 当作**不可清理**（保守策略：宁可少删，也不能删掉正在跑的
    任务正在用的中间文件）。
    """
    if not task_id:
        return None
    if task_id in cache:
        return cache[task_id]
    status: str | None = None
    path = _note_output_dir() / f"{task_id}.status.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("status") if isinstance(data, dict) else None
        if isinstance(raw, str) and raw:
            status = raw.upper()
    except FileNotFoundError:
        status = None
    except (OSError, ValueError):
        logger.warning(
            "读取任务状态文件失败，其资源本轮不可清理: %s", path, exc_info=True
        )
        status = None
    cache[task_id] = status
    return status


def _guard_within(root: Path, target: Path) -> None:
    """受管根目录越界防护（目录版）。

    `_managed_relative` 只能校验**文件**（末尾有 `resolved.is_file()`），而
    `visual_cache/<task_id>/<key>` 这类待回收对象是目录，所以这里复刻同一套
    词法 + 符号链接 + resolve 三重检查，只去掉「必须是文件」这一条。
    """
    raw = Path(os.path.abspath(target))
    try:
        relative = raw.relative_to(root)
    except ValueError as exc:
        raise ValueError("path is outside its managed root") from exc
    if not relative.parts or any(part in (".", "..") for part in relative.parts):
        raise ValueError("path contains traversal")
    if root.is_symlink():
        raise ValueError("managed root is a symbolic link")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("path contains a symbolic link")
    resolved = raw.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("path is outside its managed root")


def _dir_size(path: Path) -> int:
    """目录递归字节数；单个文件 stat 失败按 0 计（不因为一个坏文件中断整轮统计）。"""
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_symlink() or not item.is_file():
                continue
            try:
                total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        return total
    return total


def _entry_size(path: Path) -> tuple[int, float]:
    """返回 (字节数, mtime)；stat 失败返回 (0, 0.0)。"""
    try:
        stat = path.stat()
    except OSError:
        return 0, 0.0
    if path.is_dir():
        return _dir_size(path), stat.st_mtime
    return stat.st_size, stat.st_mtime


def _registered_row_fields(row) -> tuple[int, str, str | None, int, float]:
    """把一条 `MediaResource` 行拍平成纯 Python 值：`(id, path, task_id, size, created_ts)`。

    为什么需要这层：SQLAlchemy 2.x 的声明式属性在静态分析里被推断成 `Column[...]`
    而不是实例值的 `int` / `str` / `datetime`，直接解包会把这类噪音一路带进后面的
    比较与算术。这里显式转成基础类型，顺带兜住 NULL（`size_bytes` 可能为空）。
    """
    created_at = row.created_at
    created_ts = created_at.timestamp() if created_at is not None else 0.0
    return (
        _as_non_negative_int(row.id, 0),
        str(row.path),
        str(row.task_id) if row.task_id else None,
        _as_non_negative_int(row.size_bytes, 0),
        created_ts,
    )


def _collect_cache_entries() -> list[dict]:
    """扫描容量维度覆盖的全部对象，产出待选清单（不改动磁盘）。

    覆盖 spec 007 §12.1 决策 15 的六类：已登记三类资源 + visual_cache +
    uploads + note_output + 系统 temp 的 ASR 切片 + 0 字节残骸。
    同一物理路径被多个视角看到时只算一次（按 resolve 后的路径去重），可清理性
    取「更宽松」的那一档。
    """
    entries: dict[str, dict] = {}
    status_cache: dict[str, str | None] = {}

    def add(
        path: Path,
        size: int,
        mtime: float,
        kind: str,
        root: Path | None,
        deletable: bool,
        reason: str,
        row_id: int | None = None,
        db_key: str | None = None,
        sort_ts: float | None = None,
    ) -> None:
        try:
            key = str(Path(path).resolve())
        except OSError:
            key = str(path)
        existing = entries.get(key)
        if existing is not None:
            if deletable and not existing["deletable"]:
                existing["deletable"] = True
                existing["reason"] = reason
            return
        entries[key] = {
            "path": Path(path),
            "key": db_key,
            "root": root,
            "row_id": row_id,
            "kind": kind,
            "size": _as_non_negative_int(size, 0),
            "mtime": mtime,
            "deletable": deletable,
            "reason": reason,
            "sort_ts": sort_ts if sort_ts is not None else mtime,
        }

    # --- 1) 已登记的三类资源（screenshot / video / audio） ---------------------
    # 这些走 DB 登记表，删除时必须复用 `_managed_relative` 的路径防护。
    roots = _roots()
    try:
        with SessionLocal() as db:
            row_snapshot = [
                _registered_row_fields(row)
                # pi-lens-ignore: python-sql-injection
                for row in db.query(MediaResource)
                .filter(MediaResource.delete_state.in_(["active", "failed"]))
                .all()
            ]
    except Exception:
        logger.exception("读取已登记媒体资源失败，本轮容量统计跳过登记资源")
        row_snapshot = []
    for row_id, db_key, task_id, size_bytes, created_ts in row_snapshot:
        kind, separator, relative = db_key.partition(":")
        root = roots.get(kind)
        if not separator or root is None:
            # 非法键由时间维度清理负责标 failed；容量维度不碰它，避免两套逻辑
            # 对同一行的 last_error 互相覆盖。
            continue
        path = root / relative
        on_disk_size, mtime = _entry_size(path)
        status = _task_status(task_id, status_cache)
        deletable = status in _TERMINAL_STATUSES
        add(
            path,
            on_disk_size or size_bytes,
            mtime or created_ts,
            kind,
            root,
            deletable,
            "" if deletable else f"task status={status or 'unknown'}",
            row_id=row_id,
            db_key=db_key,
            sort_ts=created_ts or None,
        )

    # --- 2) visual_cache ------------------------------------------------------
    # 目录不能塞进 media_resources（`_managed_relative` 只收文件），所以独立扫描。
    # 结构：visual_cache/v1/<task_id>/<cache_key>（video_reader.py:365-367），
    # 以及写缓存中途被打断留下的 `<cache_key>.tmp-<uuid>`。
    cache_root: Path | None = None
    try:
        from app.utils.path_helper import get_app_dir

        cache_root = Path(get_app_dir(os.path.join("visual_cache", "v1"))).resolve()
    except Exception:
        logger.warning("定位 visual_cache 目录失败，本轮跳过", exc_info=True)
    if cache_root is not None and cache_root.is_dir():
        try:
            task_dirs = [
                item
                for item in cache_root.iterdir()
                if item.is_dir() and not item.is_symlink()
            ]
        except OSError:
            task_dirs = []
        for task_dir in task_dirs:
            status = _task_status(task_dir.name, status_cache)
            terminal = status in _TERMINAL_STATUSES
            try:
                children = list(task_dir.iterdir())
            except OSError:
                continue
            for child in children:
                if child.is_symlink():
                    continue
                size, mtime = _entry_size(child)
                if ".tmp-" in child.name:
                    # 暂存目录：正常路径会被 rename 成正式条目。残留说明进程被打断过，
                    # 但另一个进程可能正在写同名暂存目录，所以按 mtime 宽限后再删。
                    deletable = (time.time() - mtime) > _VISUAL_CACHE_TMP_GRACE_SECONDS
                    reason = "" if deletable else "temporary cache dir still recent"
                else:
                    deletable = terminal
                    reason = "" if deletable else f"task status={status or 'unknown'}"
                add(child, size, mtime, "visual_cache", cache_root, deletable, reason)

    # --- 3) uploads / note_output / 4) 0 字节残骸 -----------------------------
    uploads_root = Path("uploads").resolve()
    note_output_root = _note_export_dir()
    for root, kind in ((uploads_root, "uploads"), (note_output_root, "note_output")):
        if not root.is_dir():
            continue
        try:
            files = [
                item
                for item in root.rglob("*")
                if item.is_file() and not item.is_symlink()
            ]
        except OSError:
            files = []
        for item in files:
            size, mtime = _entry_size(item)
            age = time.time() - mtime
            # 这些文件没有 task 归属，无法用状态文件判断是否在用，只能用 mtime 宽限。
            deletable = age > _UNATTRIBUTED_GRACE_SECONDS
            add(
                item,
                size,
                mtime,
                kind,
                root,
                deletable,
                "" if deletable else "recently modified",
            )

    # 0 字节残骸：失败的下游写出（下载中断、ffmpeg 半成品）会留下 0 字节文件，
    # 它们永远不被任何清理器看到。给一小时宽限，避免删掉「刚创建、马上要写」的中间态。
    zero_byte_roots = [uploads_root, note_output_root]
    if cache_root is not None:
        zero_byte_roots.append(cache_root)
    zero_byte_roots.extend(roots.values())
    for root in zero_byte_roots:
        if not root.is_dir():
            continue
        try:
            files = [
                item
                for item in root.rglob("*")
                if item.is_file() and not item.is_symlink()
            ]
        except OSError:
            continue
        for item in files:
            size, mtime = _entry_size(item)
            if size != 0:
                continue
            deletable = (time.time() - mtime) > _ZERO_BYTE_GRACE_SECONDS
            add(
                item,
                0,
                mtime,
                "zero_byte",
                root,
                deletable,
                "" if deletable else "recently created",
            )

    # --- 5) 系统 temp 里的 ASR 切片目录 ---------------------------------------
    # audio_helper.py 用 mkdtemp(prefix="asr_chunks_"/"asr_speech_") 建临时目录，
    # 由调用方负责删除；任务异常中断时就会永久留在 %TEMP%。转写中的任务会持续
    # 往目录里写，mtime 因此不断更新 —— 用宽限保护正在跑的长音频转写。
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        temp_children = list(temp_root.iterdir())
    except OSError:
        temp_children = []
    for child in temp_children:
        if not child.name.startswith(("asr_chunks_", "asr_speech_")):
            continue
        if child.is_symlink():
            continue
        size, mtime = _entry_size(child)
        deletable = (time.time() - mtime) > _TEMP_GRACE_SECONDS
        add(
            child,
            size,
            mtime,
            "asr_temp",
            temp_root,
            deletable,
            "" if deletable else "transcription may be in progress",
        )

    return list(entries.values())


def _summarize(entries: list[dict], limit_bytes: int) -> dict:
    total = sum(entry["size"] for entry in entries)
    deletable = [entry for entry in entries if entry["deletable"]]
    skipped = [entry for entry in entries if not entry["deletable"]]
    target = _as_non_negative_int(limit_bytes * _CACHE_LOW_WATER_RATIO, 0)
    # 最旧优先：登记的按 created_at，磁盘文件按 mtime。
    ordered = sorted(deletable, key=lambda entry: (entry["sort_ts"], entry["kind"]))
    freed = 0
    planned: list[dict] = []
    for entry in ordered:
        if total - freed <= target:
            break
        freed += entry["size"]
        planned.append(entry)
    by_kind: dict[str, dict[str, int]] = {}
    for entry in entries:
        bucket = by_kind.setdefault(
            entry["kind"], {"count": 0, "bytes": 0, "deletable_bytes": 0}
        )
        bucket["count"] += 1
        bucket["bytes"] += entry["size"]
        if entry["deletable"]:
            bucket["deletable_bytes"] += entry["size"]
    return {
        "limit_bytes": limit_bytes,
        "low_water_bytes": target,
        "total_bytes": total,
        "over_limit": total > limit_bytes,
        "deletable_count": len(deletable),
        "deletable_bytes": sum(entry["size"] for entry in deletable),
        "skipped_count": len(skipped),
        "skipped_bytes": sum(entry["size"] for entry in skipped),
        "planned": planned,
        "would_delete_count": len(planned),
        "would_delete_bytes": sum(entry["size"] for entry in planned),
        "by_kind": by_kind,
        "skipped_samples": [
            {
                "kind": entry["kind"],
                "path": str(entry["path"]),
                "reason": entry["reason"],
            }
            for entry in sorted(skipped, key=lambda entry: entry["size"], reverse=True)[
                :_SKIPPED_SAMPLE_LIMIT
            ]
        ],
    }


def _drop_registered_row(row_id: int) -> None:
    with SessionLocal() as db:
        row = db.get(MediaResource, row_id)
        if row is not None:
            db.delete(row)
            db.commit()


def _mark_registered_row_failed(row_id: int, message: str) -> None:
    with SessionLocal() as db:
        row = db.get(MediaResource, row_id)
        if row is not None:
            _mark_row_failed(row, message)
            db.commit()


def _delete_entry(entry: dict) -> str:
    """删除一个候选对象，返回 'deleted' / 'missing' / 'failed'。

    所有删除都必须先过路径防护：已登记资源复用 `_managed_relative`（与时间维度
    清理同一套，绝不绕过），其余目录/文件走 `_guard_within`。
    """
    path = Path(entry["path"])
    if entry["row_id"] is not None:
        kind, _separator, relative = (entry["key"] or "").partition(":")
        root = _roots().get(kind)
        if root is None:
            return "failed"
        target = root / relative
        if not target.exists():
            _drop_registered_row(entry["row_id"])
            return "missing"
        try:
            _managed_relative(kind, target)
        except ValueError as exc:
            _mark_registered_row_failed(entry["row_id"], str(exc)[:1000])
            return "failed"
        try:
            target.unlink()
        except OSError as exc:
            _mark_registered_row_failed(entry["row_id"], str(exc)[:1000])
            return "failed"
        _drop_registered_row(entry["row_id"])
        return "deleted"

    root = entry["root"]
    if root is None:
        return "failed"
    try:
        _guard_within(Path(root), path)
    except ValueError:
        logger.warning("容量清理跳过越界路径: %s", path)
        return "failed"
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            return "missing"
    except OSError as exc:
        logger.warning("容量清理删除失败: %s (%s)", path, exc)
        return "failed"
    return "deleted"


def _record_capacity_audit(report: dict, requested: int) -> None:
    try:
        from app.db.models.media_cleanup_run import MediaCleanupRun

        with SessionLocal() as db:
            db.add(
                MediaCleanupRun(
                    # 触发原因靠 resource_types 前缀区分：容量维度固定写 "capacity"，
                    # 时间维度写 "screenshot,video,audio"。`expired_only` 容量维度恒为
                    # False（容量清理不等过期），单看它无法区分两种触发。
                    resource_types="capacity",
                    expired_only=False,
                    deleted=report["deleted"],
                    missing=report["missing"],
                    failed=report["failed"],
                    bytes_freed=report["bytes_freed"],
                    requested=requested,
                    completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            db.commit()
    except Exception:
        logger.exception("Failed to persist capacity cleanup audit report")


def preview_cache_limit() -> dict:
    """只读观测：当前总占用 / 上限 / 若触发会删多少。不删任何文件、不写审计行。"""
    return enforce_cache_limit(dry_run=True)


def enforce_cache_limit(dry_run: bool = False) -> dict:
    """按容量边界回收本地媒体缓存（spec 007 §12 / spec 009 ticket 07）。

    给谁用、什么时候调：

    * `media_cleanup_loop`（本模块）—— 每轮时间维度清理之后追加一次；
    * **任务到达终态时的钩子** —— `SUCCESS` 与 `FAILED` 落盘之后调一次。调用点
      在 `app/routers/note.py` 一侧（本模块刻意不 import 路由，也不自己接），
      目的是让刚跑完的长任务立刻释放空间，而不是干等下一小时的那轮循环；
    * HTTP 观测 / 手动触发端点 —— `app/routers/media.py`。

    同步阻塞实现（要扫目录 + 删文件），异步上下文请用
    `await asyncio.to_thread(enforce_cache_limit)`，不要直接 await 它。

    `cache_limit_bytes == 0` 表示不设上限：直接跳过容量维度，完全不影响既有
    时间维度清理。超限时按最旧优先删到上限的 `_CACHE_LOW_WATER_RATIO`（90%）。
    `dry_run=True` 只算不删（观测用）。
    """
    settings = get_cache_settings()
    limit_bytes = settings["cache_limit_bytes"]
    disk: dict[str, int | None] = {
        "free_bytes": None,
        "min_free_disk_bytes": settings["min_free_disk_bytes"],
    }
    try:
        usage = shutil.disk_usage(str(Path.cwd()))
        disk["free_bytes"] = usage.free
    except OSError as exc:
        # 取不到剩余磁盘空间不能影响容量清理本身（它只依赖 cache_limit_bytes）。
        # 这里**刻意不写 `pass`**：留一条日志才能区分「磁盘真的没空间」与
        # 「这次没读到」，否则观测端点上的 free_bytes=None 会无从解释。
        logger.warning("读取磁盘剩余空间失败，本轮跳过最低剩余空间判断：%s", exc)

    report: dict = {
        "dry_run": dry_run,
        "enabled": limit_bytes > 0,
        "limit_bytes": limit_bytes,
        "low_water_bytes": _as_non_negative_int(
            limit_bytes * _CACHE_LOW_WATER_RATIO, 0
        ),
        "total_bytes": 0,
        "over_limit": False,
        "deletable_count": 0,
        "deletable_bytes": 0,
        "skipped_count": 0,
        "skipped_bytes": 0,
        "would_delete_count": 0,
        "would_delete_bytes": 0,
        "deleted": 0,
        "missing": 0,
        "failed": 0,
        "bytes_freed": 0,
        "by_kind": {},
        "skipped_samples": [],
        "disk": disk,
        "circuit_breaker_threshold": settings["circuit_breaker_threshold"],
    }

    if limit_bytes <= 0:
        # 0 = 不设上限。注意这里必须**在扫描之前**返回：既省一次全盘扫描，
        # 也保证「关掉容量维度」的行为是彻底的 no-op。
        logger.info("容量边界清理已关闭（cache_limit_bytes=0），跳过容量维度")
        return report

    entries = _collect_cache_entries()
    summary = _summarize(entries, limit_bytes)
    report.update(
        {
            key: summary[key]
            for key in (
                "total_bytes",
                "over_limit",
                "deletable_count",
                "deletable_bytes",
                "skipped_count",
                "skipped_bytes",
                "would_delete_count",
                "would_delete_bytes",
                "by_kind",
                "skipped_samples",
            )
        }
    )
    report["requested"] = len(entries)

    if not summary["over_limit"]:
        logger.info(
            "容量边界未超限: total=%s limit=%s entries=%s",
            summary["total_bytes"],
            limit_bytes,
            len(entries),
        )
        return report

    if dry_run:
        return report

    for entry in summary["planned"]:
        outcome = _delete_entry(entry)
        if outcome == "deleted":
            report["deleted"] += 1
            report["bytes_freed"] += entry["size"]
        elif outcome == "missing":
            report["missing"] += 1
        else:
            report["failed"] += 1

    logger.info(
        "容量边界清理完成: limit=%s total_before=%s deleted=%s missing=%s failed=%s bytes_freed=%s",
        limit_bytes,
        summary["total_bytes"],
        report["deleted"],
        report["missing"],
        report["failed"],
        report["bytes_freed"],
    )
    _record_capacity_audit(report, requested=len(entries))
    return report


async def media_cleanup_loop(stop_event, interval_seconds: int = 3600) -> None:
    import asyncio

    while not stop_event.is_set():
        try:
            await asyncio.to_thread(cleanup_resources, None, True, 200)
        except Exception:
            logger.exception("Scheduled media cleanup failed")
        try:
            # 容量维度：每轮到期清理之后再跑一次。两件事都丢进线程池，语义与既有的
            # `asyncio.to_thread` 模式一致，不会阻塞事件循环。失败只记日志，不影响
            # 下一轮 —— 清理是尽力而为的后台工作。
            await asyncio.to_thread(enforce_cache_limit)
        except Exception:
            logger.exception("Scheduled cache limit enforcement failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        # pi-lens-ignore: ast-grep:no-bare-except
        except asyncio.TimeoutError:
            continue
