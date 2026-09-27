"""Register and safely clean files inside configured media roots."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from app.db.engine import SessionLocal
from app.db.models.media_resources import MediaResource
from app.utils.logger import get_logger

logger = get_logger(__name__)


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


def get_retention_settings() -> dict[str, int]:
    from app.db.models.media_settings import MediaSettings

    with SessionLocal() as db:
        row = db.query(MediaSettings).filter_by(id=1).one_or_none()
        if row:
            return {
                "screenshot_retention_days": row.screenshot_retention_days,
                "media_retention_days": row.media_retention_days,
            }
    return {
        "screenshot_retention_days": int(os.getenv("SCREENSHOT_RETENTION_DAYS", "7")),
        "media_retention_days": int(os.getenv("MEDIA_RETENTION_DAYS", "3")),
    }


def set_retention_settings(screenshot_days: int, media_days: int) -> dict[str, int]:
    from app.db.models.media_settings import MediaSettings

    if screenshot_days < 0 or media_days < 0:
        raise ValueError("保留天数必须为非负整数")
    with SessionLocal() as db:
        row = db.query(MediaSettings).filter_by(id=1).one_or_none()
        if row is None:
            row = MediaSettings(id=1)
            db.add(row)
        row.screenshot_retention_days = screenshot_days
        row.media_retention_days = media_days
        db.commit()
    return {"screenshot_retention_days": screenshot_days, "media_retention_days": media_days}


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
    days = settings["screenshot_retention_days" if resource_type == "screenshot" else "media_retention_days"]
    expires = created + timedelta(days=days) if days else None
    key = f"{resource_type}:{relative}"
    with SessionLocal() as db:
        if db.query(MediaResource.id).filter_by(path=key).first():
            return
        db.add(MediaResource(
            resource_type=resource_type,
            task_id=task_id,
            video_id=video_id,
            path=key,
            size_bytes=path.stat().st_size,
            created_at=created,
            expires_at=expires,
            source=source,
        ))
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
                if path.is_symlink() or not path.is_file() or path.suffix.lower() not in extensions[kind]:
                    continue
                try:
                    before = _count_path(kind, path)
                    created = datetime.fromtimestamp(path.stat().st_mtime)
                    register_resource(kind, path, created_at=created, source="legacy_backfill")
                    inserted += int(_count_path(kind, path) > before)
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


def preview_cleanup(resource_types: list[str] | None = None, expired_only: bool = True) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    selected = _selected_types(resource_types)
    with SessionLocal() as db:
        query = db.query(MediaResource).filter(
            MediaResource.resource_type.in_(selected),
            MediaResource.delete_state.in_(["active", "failed"]),
        )
        if expired_only:
            query = query.filter(MediaResource.expires_at.isnot(None), MediaResource.expires_at <= now)
        rows = query.all()
    return {
        "count": len(rows),
        "bytes": sum(row.size_bytes for row in rows),
        "by_type": {
            kind: {
                "count": sum(row.resource_type == kind for row in rows),
                "bytes": sum(row.size_bytes for row in rows if row.resource_type == kind),
            }
            for kind in selected
        },
        "expires_earliest": min((row.expires_at for row in rows if row.expires_at), default=None),
        "expires_latest": max((row.expires_at for row in rows if row.expires_at), default=None),
    }


def get_recent_cleanup_runs(limit: int = 10) -> list[dict]:
    from app.db.models.media_cleanup_run import MediaCleanupRun

    with SessionLocal() as db:
        rows = db.query(MediaCleanupRun).order_by(
            MediaCleanupRun.completed_at.desc(), MediaCleanupRun.id.desc()
        ).limit(max(1, min(limit, 50))).all()
        return [{
            "resource_types": row.resource_types.split(",") if row.resource_types else [],
            "expired_only": row.expired_only,
            "deleted": row.deleted,
            "missing": row.missing,
            "failed": row.failed,
            "bytes_freed": row.bytes_freed,
            "requested": row.requested,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        } for row in rows]


def cleanup_resources(
    resource_types: list[str] | None = None,
    expired_only: bool = True,
    limit: int = 200,
) -> dict:
    selected = _selected_types(resource_types)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    report = {"deleted": 0, "missing": 0, "failed": 0, "bytes": 0, "requested": 0}
    with SessionLocal() as db:
        query = db.query(MediaResource).filter(
            MediaResource.resource_type.in_(selected),
            MediaResource.delete_state.in_(["active", "failed"]),
        )
        if expired_only:
            query = query.filter(MediaResource.expires_at.isnot(None), MediaResource.expires_at <= now)
        rows = query.order_by(MediaResource.id).limit(max(1, min(limit, 1000))).all()
        report["requested"] = len(rows)
        roots = _roots()
        for row in rows:
            kind, separator, relative = row.path.partition(":")
            root = roots.get(kind)
            if not separator or root is None:
                row.delete_state, row.last_error = "failed", "invalid managed resource key"
                report["failed"] += 1
                continue
            raw_target = root / relative
            try:
                lexical_relative = raw_target.relative_to(root)
                if not lexical_relative.parts or any(part in (".", "..") for part in lexical_relative.parts):
                    raise ValueError("invalid relative path")
                cursor = root
                if root.is_symlink():
                    raise ValueError("managed root is a symbolic link")
                for part in lexical_relative.parts:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        raise ValueError("managed path contains a symbolic link")
            except ValueError:
                row.delete_state, row.last_error = "failed", "managed path escaped root or contains a symbolic link"
                report["failed"] += 1
                continue
            target = raw_target.resolve()
            if target == root or root not in target.parents:
                row.delete_state, row.last_error = "failed", "managed path escaped root"
                report["failed"] += 1
                continue
            try:
                if target.exists():
                    target.unlink()
                    report["deleted"] += 1
                    report["bytes"] += row.size_bytes
                else:
                    report["missing"] += 1
                db.delete(row)
            except OSError as exc:
                row.delete_state, row.last_error = "failed", str(exc)[:1000]
                report["failed"] += 1
        db.commit()

    logger.info(
        "Media cleanup completed: types=%s expired_only=%s deleted=%s missing=%s failed=%s bytes=%s",
        selected, expired_only, report["deleted"], report["missing"], report["failed"], report["bytes"],
    )
    try:
        from app.db.models.media_cleanup_run import MediaCleanupRun

        with SessionLocal() as db:
            db.add(MediaCleanupRun(
                resource_types=",".join(selected),
                expired_only=expired_only,
                deleted=report["deleted"],
                missing=report["missing"],
                failed=report["failed"],
                bytes_freed=report["bytes"],
                requested=report["requested"],
                completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ))
            db.commit()
    except Exception:
        logger.exception("Failed to persist media cleanup audit report")
    return report


async def media_cleanup_loop(stop_event, interval_seconds: int = 3600) -> None:
    import asyncio

    while not stop_event.is_set():
        try:
            await asyncio.to_thread(cleanup_resources, None, True, 200)
        except Exception:
            logger.exception("Scheduled media cleanup failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            continue



