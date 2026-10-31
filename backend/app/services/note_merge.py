"""合并笔记：把多个视频的笔记合成一篇（spec 018）。

设计约束（用户决策 2026-10-18）：

* **默认结构拼接**：不额外调用模型 —— 多个视频的笔记各自已经由模型写过，
  再让模型「融合」一次既慢又容易丢截图锚点和细节。拼接保留原文，代价是跨视频
  的去重/串联做不到，这一点写进 spec 的已定决策里。
* **模型润色是可选开关**：需要一篇更连贯的成稿时，`merge_polish=true` 再把拼接
  结果整体交给当前模型改写一次（见 `UniversalGPT.polish_markdown`）。
* 本模块只做**纯文本/纯数据**变换，不碰数据库、网络与状态文件，方便单测。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.models.audio_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment

#: 代码围栏起始行（``` 或 ~~~，允许缩进）。围栏内的 `#` 是注释/标题语法，
#: 不是 Markdown 标题，降级时必须原样跳过 —— 否则代码块会被改坏。
_FENCE_RE = re.compile(r"^\s*(\x60{3,}|~{3,})")
#: Markdown ATX 标题：1–6 个 # 后跟空白。
_HEADING_RE = re.compile(r"^(#{1,6})(\s+.*)$")


@dataclass
class MergedEntry:
    """一个待合并的视频笔记。"""

    title: str
    markdown: str
    duration: float = 0.0
    video_id: str = ""
    cover_url: str | None = None
    transcript: TranscriptResult | None = None
    source_url: str = ""


@dataclass
class MergedFailure:
    """一个生成失败的视频（进笔记末尾的清单）。"""

    title: str
    reason: str = ""


def _as_seconds(value) -> float:
    """音频元数据里的时长可能是 None / '12:34' / 空串，统一收敛成秒。"""
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _format_duration(seconds: float) -> str:
    total = int(_as_seconds(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def demote_headings(markdown: str, levels: int = 1) -> str:
    """把 Markdown 标题整体降 `levels` 级（代码围栏内不动）。

    为什么需要：合并后每个视频的正文都挂在一个 `## 视频标题` 之下，如果正文里
    自带 `# 一级标题`，读者会看到同一层出现多个「根」，大纲也就乱了。
    降级到 6 级封顶（Markdown 没有 7 级标题）。
    """
    if not markdown or levels <= 0:
        return markdown

    out: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        match = _HEADING_RE.match(line)
        if not match:
            out.append(line)
            continue
        hashes, rest = match.group(1), match.group(2)
        out.append("#" * min(6, len(hashes) + levels) + rest)
    return "\n".join(out)


def _strip_leading_heading(markdown: str) -> str:
    """去掉正文开头的第一个一级标题（合并时标题由我们自己给）。

    只处理「第一个非空行是一级标题」这一种情况：模型经常把视频标题写成
    `# 标题` 起头，原样保留会在合并笔记里出现两级同名标题。
    """
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        if re.match(r"^#\s+", line):
            return "\n".join(lines[index + 1 :]).lstrip("\n")
        return markdown
    return markdown


def _toc_lines(entries: list[MergedEntry]) -> list[str]:
    lines = ["## 目录", ""]
    for index, entry in enumerate(entries, start=1):
        suffix = f"（{_format_duration(entry.duration)}）" if entry.duration else ""
        lines.append(f"{index}. {entry.title or f'视频 {index}'}{suffix}")
    lines.append("")
    return lines


def build_merged_markdown(
    title: str,
    entries: Iterable[MergedEntry],
    failures: Iterable[MergedFailure] = (),
    toc: bool = True,
) -> str:
    """把多个视频笔记拼成一篇。

    结构：`# 合并标题` → 目录 → 每个视频 `## i. 标题` → 正文（标题降一级），
    失败项统一列在末尾。条目之间用 `---` 分隔，避免上一段的列表/引用粘到下一段。
    """
    items = list(entries)
    failed = list(failures)

    parts: list[str] = [f"# {title}".rstrip(), ""]
    if items:
        parts.append(f"> 本笔记由 {len(items)} 个视频的笔记合并而成。")
        parts.append("")

    if toc and len(items) > 1:
        parts.extend(_toc_lines(items))

    for index, entry in enumerate(items, start=1):
        heading = entry.title or f"视频 {index}"
        parts.append("---")
        parts.append("")
        parts.append(f"## {index}. {heading}")
        if entry.source_url:
            parts.append("")
            parts.append(f"> 来源：{entry.source_url}")
        parts.append("")
        body = demote_headings(_strip_leading_heading(entry.markdown or ""), 1).strip()
        parts.append(body if body else "_（这篇笔记没有正文）_")
        parts.append("")

    if failed:
        parts.append("---")
        parts.append("")
        parts.append("## 未生成成功的视频")
        parts.append("")
        parts.append("以下视频这次没有生成成功，可以稍后单独重试：")
        parts.append("")
        for item in failed:
            reason = f"（{item.reason}）" if item.reason else ""
            parts.append(f"- {item.title}{reason}")
        parts.append("")

    return "\n".join(parts).strip() + "\n"


def merge_transcripts(entries: Iterable[MergedEntry]) -> TranscriptResult:
    """把各视频转写拼成一份：`full_text` 带小标题，`segments` 前插分隔段。

    时间轴**不做偏移**：每个视频的秒数都是相对自己视频的，硬拼成一条连续时间轴
    会给出错误的定位。改成在每个视频前插一条分隔段，读者仍能看出「换了一个视频」。
    """
    items = list(entries)
    full_texts: list[str] = []
    segments: list[TranscriptSegment] = []
    language: str | None = None

    for index, entry in enumerate(items, start=1):
        transcript = entry.transcript
        if transcript is None:
            continue
        if language is None and transcript.language:
            language = transcript.language
        heading = entry.title or f"视频 {index}"
        text = (transcript.full_text or "").strip()
        if text:
            full_texts.append(f"## {index}. {heading}\n\n{text}")
        segments.append(
            TranscriptSegment(
                start=0.0, end=0.0, text=f"—— 第 {index} 个视频：{heading} ——"
            )
        )
        segments.extend(transcript.segments or [])

    return TranscriptResult(
        language=language or "zh",
        full_text="\n\n".join(full_texts),
        segments=segments,
        raw=None,
    )


def build_merged_audio_meta(
    title: str,
    entries: Iterable[MergedEntry],
    platform: str = "bilibili",
    video_id: str = "",
) -> AudioDownloadResult:
    """合并任务的 audio_meta。

    任务列表标题取自 `audio_meta.title`（见 `_result_title`），所以这里必须是
    合并标题而不是第一个视频的标题。`file_path` 留空：合并产物没有单一音视频文件。
    """
    items = list(entries)
    duration = sum(_as_seconds(item.duration) for item in items)
    cover = next((item.cover_url for item in items if item.cover_url), None)
    return AudioDownloadResult(
        file_path="",
        title=title,
        duration=duration,
        cover_url=cover,
        platform=platform,
        video_id=video_id,
        raw_info={
            "merged": True,
            "merged_from": [item.video_id for item in items if item.video_id],
        },
        video_path=None,
    )
