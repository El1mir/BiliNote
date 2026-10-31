"""Platform-neutral source intake with a Bilibili adapter."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse

from app.utils.url_parser import (
    extract_bilibili_p_number,
    extract_video_id,
    normalize_video_url,
    parse_bilibili_collection_url,
    resolve_bilibili_short_url,
)

SCHEMA_VERSION = 1
DEFAULT_LIMITS = {
    "maxInputUrls": 200,
    "maxExpandedItems": 500,
    "maxResolveConcurrency": 4,
    "resolveTimeoutMs": 120000,
}


@dataclass(frozen=True)
class IntakeItem:
    item_id: str
    client_index: int
    raw_url: str
    canonical_url: str | None
    source: str
    kind: str
    source_id: str | None
    parent_item_id: str | None
    part: int | None
    state: str
    error: dict[str, Any] | None = None
    duplicate_of: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value.update(
            {
                "itemId": value.pop("item_id"),
                "clientIndex": value.pop("client_index"),
                "canonicalUrl": value.pop("canonical_url"),
                "sourceId": value.pop("source_id"),
                "parentItemId": value.pop("parent_item_id"),
                "duplicateOf": value.pop("duplicate_of"),
            }
        )
        return value


def _error(code: str, message_key: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "messageKey": message_key, "params": params}


def _is_bilibili(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv"


def _item_id(index: int, suffix: str = "") -> str:
    return f"intake-{index}{suffix}"


def resolve_bilibili_inputs(
    urls: list[str], *, limits: dict[str, int] | None = None
) -> dict[str, Any]:
    """Resolve user URLs into ordered, deduplicated canonical intake items."""
    active_limits = {**DEFAULT_LIMITS, **(limits or {})}
    items: list[IntakeItem] = []
    seen: dict[str, str] = {}
    expanded_count = 0

    for client_index, original in enumerate(urls):
        raw_url = str(original).strip()
        base_id = _item_id(client_index)
        if not raw_url:
            items.append(
                IntakeItem(
                    base_id,
                    client_index,
                    raw_url,
                    None,
                    "unknown",
                    "invalid",
                    None,
                    None,
                    None,
                    "invalid",
                    _error("empty_input", "errors.intake.emptyInput"),
                )
            )
            continue
        if not _is_bilibili(raw_url):
            items.append(
                IntakeItem(
                    base_id,
                    client_index,
                    raw_url,
                    None,
                    "unknown",
                    "unsupported",
                    None,
                    None,
                    None,
                    "unsupported",
                    _error("unsupported_source", "errors.intake.unsupportedSource"),
                )
            )
            continue

        resolved = (
            resolve_bilibili_short_url(raw_url) if "b23.tv" in raw_url else raw_url
        )
        if "b23.tv" in raw_url and not resolved:
            items.append(
                IntakeItem(
                    base_id,
                    client_index,
                    raw_url,
                    None,
                    "bilibili",
                    "invalid",
                    None,
                    None,
                    None,
                    "invalid",
                    _error("short_url_unresolved", "errors.intake.shortUrlUnresolved"),
                )
            )
            continue
        normalized = normalize_video_url(resolved or raw_url)
        bvid = extract_video_id(normalized, "bilibili")
        collection = parse_bilibili_collection_url(raw_url)
        if collection:
            if expanded_count >= active_limits["maxExpandedItems"]:
                items.append(
                    IntakeItem(
                        base_id,
                        client_index,
                        raw_url,
                        None,
                        "bilibili",
                        collection.get("type", "collection"),
                        str(collection.get("sid")),
                        None,
                        None,
                        "limit_exceeded",
                        _error(
                            "collection_limit_exceeded",
                            "errors.intake.collectionLimitExceeded",
                        ),
                    )
                )
                continue
            items.append(
                IntakeItem(
                    base_id,
                    client_index,
                    raw_url,
                    raw_url,
                    "bilibili",
                    collection.get("type", "collection"),
                    str(collection.get("sid")),
                    None,
                    None,
                    "ready",
                )
            )
            expanded_count += 1
            continue
        if not bvid:
            items.append(
                IntakeItem(
                    base_id,
                    client_index,
                    raw_url,
                    None,
                    "bilibili",
                    "invalid",
                    None,
                    None,
                    None,
                    "invalid",
                    _error("invalid_url", "errors.intake.invalidUrl"),
                )
            )
            continue
        part = extract_bilibili_p_number(normalized)
        key = f"bilibili:{bvid}:{part or 0}"
        duplicate_of = seen.get(key)
        state = "duplicate" if duplicate_of else "ready"
        if not duplicate_of:
            seen[key] = base_id
        items.append(
            IntakeItem(
                base_id,
                client_index,
                raw_url,
                normalized,
                "bilibili",
                "part" if part else "video",
                bvid,
                None,
                part,
                state,
                _error("duplicate_item", "errors.intake.duplicateItem")
                if duplicate_of
                else None,
                duplicate_of,
            )
        )
        expanded_count += 1

    if len(urls) > active_limits["maxInputUrls"]:
        for index in range(active_limits["maxInputUrls"], len(items)):
            item = items[index]
            items[index] = IntakeItem(
                item.item_id,
                item.client_index,
                item.raw_url,
                None,
                item.source,
                item.kind,
                item.source_id,
                item.parent_item_id,
                item.part,
                "limit_exceeded",
                _error("collection_limit_exceeded", "errors.intake.inputLimitExceeded"),
                item.duplicate_of,
            )
    summary = {
        "inputCount": len(urls),
        "readyCount": sum(item.state == "ready" for item in items),
        "invalidCount": sum(item.state == "invalid" for item in items),
        "duplicateCount": sum(item.state == "duplicate" for item in items),
        "expandedCount": expanded_count,
        "limits": active_limits,
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "source": "bilibili",
        "summary": summary,
        "items": [item.as_dict() for item in items],
    }
