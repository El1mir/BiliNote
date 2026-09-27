"""Create self-contained ZIP archives from note Markdown and local screenshot assets."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


_IMAGE_LINK_RE = re.compile(r"(?P<prefix>!\[[^\]]*\]\()(?P<url><[^>]+>|[^\s)]+)(?P<suffix>\s+(?:\"[^\"]*\"|'[^']*'))?\)")


class NoteArchiveError(ValueError):
    """The Markdown references an invalid or unavailable local asset."""


def _safe_asset_name(path: Path, used_names: set[str]) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name).strip("._") or "image"
    if name in used_names:
        digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:10]
        stem, suffix = Path(name).stem, Path(name).suffix
        name = f"{stem}-{digest}{suffix}"
    used_names.add(name)
    return name


def write_note_archive(
    markdown: str,
    screenshot_root: Path,
    output_path: Path,
    image_base_url: str = "/static/screenshots",
    max_files: int = 500,
    max_bytes: int = 512 * 1024 * 1024,
) -> tuple[int, int]:
    """Write note.md and referenced local screenshot files; return (assets, bytes)."""
    root = screenshot_root.resolve()
    base = image_base_url.rstrip("/")
    allowed_prefixes = {base}
    parsed_base = urlsplit(base)
    if parsed_base.path:
        allowed_prefixes.add(parsed_base.path.rstrip("/"))

    assets: list[tuple[str, Path]] = []
    rewritten = markdown
    used_names: set[str] = set()

    for match in list(_IMAGE_LINK_RE.finditer(markdown)):
        raw_url = match.group("url")
        url = raw_url[1:-1] if raw_url.startswith("<") and raw_url.endswith(">") else raw_url
        parsed = urlsplit(url)
        path_part = unquote(parsed.path)
        local_suffix = None
        for prefix in sorted(allowed_prefixes, key=len, reverse=True):
            if path_part == prefix or path_part.startswith(prefix + "/"):
                local_suffix = path_part[len(prefix):].lstrip("/")
                break
        if local_suffix is None:
            continue

        if root.is_symlink():
            raise NoteArchiveError("截图目录不能是符号链接")
        raw_source = root / local_suffix
        try:
            lexical_relative = raw_source.relative_to(root)
        except ValueError as exc:
            raise NoteArchiveError("本地图片路径超出截图目录：路径包含非法片段") from exc
        cursor = root
        for part in lexical_relative.parts:
            if part in (".", ".."):
                raise NoteArchiveError("本地图片路径超出截图目录：路径包含非法片段")
            cursor = cursor / part
            if cursor.is_symlink():
                raise NoteArchiveError("本地图片路径不能包含符号链接")
        source = raw_source.resolve()
        if source != root and root not in source.parents:
            raise NoteArchiveError("本地图片路径超出截图目录")
        if not source.is_file():
            raise NoteArchiveError(f"笔记引用的图片不存在：{source.name}")
        assets.append(("", source))

    if len(assets) > max_files:
        raise NoteArchiveError(f"图片数量超过归档上限（{max_files}）")
    unique_sources = set(path for _, path in assets)
    if len(unique_sources) > max_files:
        raise NoteArchiveError(f"图片数量超过归档上限（{max_files}）")
    total_bytes = sum(path.stat().st_size for path in unique_sources)
    if total_bytes > max_bytes:
        raise NoteArchiveError(f"图片总大小超过归档上限（{max_bytes} 字节）")

    source_to_name: dict[Path, str] = {}
    for _, source in assets:
        if source not in source_to_name:
            source_to_name[source] = _safe_asset_name(source, used_names)

    def replace_link(match: re.Match[str]) -> str:
        raw_url = match.group("url")
        url = raw_url[1:-1] if raw_url.startswith("<") and raw_url.endswith(">") else raw_url
        parsed = urlsplit(url)
        path_part = unquote(parsed.path)
        for prefix in sorted(allowed_prefixes, key=len, reverse=True):
            if path_part == prefix or path_part.startswith(prefix + "/"):
                relative = Path(unquote(path_part[len(prefix):].lstrip("/")))
                if relative.is_absolute() or any(part in (".", "..") for part in relative.parts):
                    return match.group(0)
                candidate = root / relative
                cursor = root
                if root.is_symlink():
                    return match.group(0)
                for part in relative.parts:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        return match.group(0)
                source = candidate.resolve()
                if source != root and root not in source.parents:
                    return match.group(0)
                name = source_to_name.get(source)
                if name:
                    return f"{match.group('prefix')}assets/{name}{match.group('suffix') or ''})"
        return match.group(0)

    rewritten = _IMAGE_LINK_RE.sub(replace_link, rewritten)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("note.md", rewritten)
        for source, name in source_to_name.items():
            archive.write(source, f"assets/{name}")
    return len(source_to_name), total_bytes



