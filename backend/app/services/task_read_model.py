"""Versioned task read model primitives.

This module keeps task status normalization and revision semantics outside the
router. The router remains an adapter around the existing status authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from threading import Lock
from typing import Any, Callable, Iterable

SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset({"SUCCESS", "FAILED", "CANCELLED"})

_STATUS_ALIASES = {
    "PENDING": "queued",
    "QUEUED": "queued",
    "RUNNING": "running",
    "PROCESSING": "running",
    "SUCCESS": "succeeded",
    "SUCCEEDED": "succeeded",
    "COMPLETED": "succeeded",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
}

#: 旧值与别名的归一化。**只做追加**：`success` / `failed` 原本被折叠成
#: `finalizing`，于是「已经走完的阶段」「失败发生在哪一步」同时丢失 —— 前端拿到
#: 一个终态聚合值，12 个阶段全显示待处理（spec 005 ticket 08）。
#: 现在终态阶段按后端写下的真实阶段值透传（`saving` / `transcribing` …，
#: 或没有在途阶段时的 `success` / `failed`），`finalizing` 仍保留给旧别名。
_PHASE_ALIASES = {
    "completed": "finalizing",
    "done": "finalizing",
}


@dataclass(frozen=True)
class TaskView:
    task_id: str
    status: str
    phase: str | None
    progress: float | None
    message: str | None
    detail: dict[str, Any] | None
    updated_at: str | None
    revision: int
    error: dict[str, Any] | None
    actions: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress,
            "message": self.message,
            "detail": self.detail,
            "updatedAt": self.updated_at,
            "revision": self.revision,
            "error": self.error,
            "actions": self.actions,
        }


def normalize_status(value: Any) -> str:
    """Map legacy backend values to the stable read-model status set."""
    key = str(value or "PENDING").strip().upper()
    return _STATUS_ALIASES.get(key, "running")


def normalize_phase(value: Any, status: str) -> str | None:
    """阶段归一化。缺值时按终态给 success / failed，不再一律 finalizing。"""
    if value is None:
        if status == "succeeded":
            return "success"
        if status == "failed":
            return "failed"
        return None
    phase = str(value).strip().lower()
    return _PHASE_ALIASES.get(phase, phase or None)


def detail_payload(value: Any) -> dict[str, Any] | None:
    """阶段详情归一化成 dict 或 None。

    后端写的一直是 dict（切片数 / 帧数 / 网格数 / 候选数），历史 payload 里也出现过
    字符串。读模型必须给出唯一的形状，前端才敢直接按键渲染：dict 原样透传，
    JSON 字符串解一次，其它字符串包成 {'text': ...}。
    """
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except ValueError:
            return {"text": text}
        if isinstance(parsed, dict):
            return parsed
        return {"text": text}
    return None


def _progress(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, number))


def _actions(status: str) -> dict[str, bool]:
    active = status in {"queued", "running"}
    return {
        "retry": status in {"failed", "cancelled"},
        "cancel": active,
        "openNote": status == "succeeded",
        "openTranscript": status == "succeeded",
        "chat": status == "succeeded",
        "export": status == "succeeded",
    }


def _error(raw: dict[str, Any], status: str) -> dict[str, Any] | None:
    if status != "failed":
        return None
    code = raw.get("error_code") or raw.get("errorCode") or "task_failed"
    message_key = raw.get("message_key") or raw.get("messageKey") or "errors.taskFailed"
    return {"code": str(code), "messageKey": str(message_key), "retryable": True}


def to_task_view(task_id: str, raw: dict[str, Any] | None, revision: int) -> TaskView:
    payload = raw or {"status": "PENDING"}
    status = normalize_status(payload.get("status"))
    return TaskView(
        task_id=task_id,
        status=status,
        phase=normalize_phase(payload.get("stage") or payload.get("phase"), status),
        progress=_progress(payload.get("progress")),
        message=payload.get("message"),
        detail=detail_payload(payload.get("detail")),
        updated_at=payload.get("updated_at") or payload.get("updatedAt"),
        revision=revision,
        error=_error(payload, status),
        actions=_actions(status),
    )


class TaskReadModel:
    """Build immutable snapshots and monotonic revisions from a status reader."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._revision = 0
        self._fingerprint = ""
        self._task_revisions: dict[str, int] = {}
        self._task_fingerprints: dict[str, str] = {}

    def snapshot(
        self,
        task_ids: Iterable[str],
        read_status: Callable[[str], dict[str, Any] | None],
        source: str = "snapshot",
    ) -> dict[str, Any]:
        ids = list(
            dict.fromkeys(
                str(task_id).strip() for task_id in task_ids if str(task_id).strip()
            )
        )
        raw_items = {task_id: read_status(task_id) for task_id in ids}
        fingerprint = sha256(
            json.dumps(raw_items, sort_keys=True, default=str).encode()
        ).hexdigest()
        with self._lock:
            if fingerprint != self._fingerprint:
                self._revision += 1
                self._fingerprint = fingerprint
            views = []
            for task_id in ids:
                task_fingerprint = sha256(
                    json.dumps(raw_items[task_id], sort_keys=True, default=str).encode()
                ).hexdigest()
                if self._task_fingerprints.get(task_id) != task_fingerprint:
                    self._task_revisions[task_id] = (
                        self._task_revisions.get(task_id, 0) + 1
                    )
                    self._task_fingerprints[task_id] = task_fingerprint
                views.append(
                    to_task_view(
                        task_id, raw_items[task_id], self._task_revisions[task_id]
                    )
                )
            revision = self._revision
        return {
            "schemaVersion": SCHEMA_VERSION,
            "snapshotRevision": revision,
            "source": source,
            "tasks": [view.as_dict() for view in views],
            "groups": [],
        }
