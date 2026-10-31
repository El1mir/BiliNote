"""spec 018：合并笔记的纯函数（标题降级 / 目录 / 失败清单 / 转写合并）。

这一层不碰数据库与网络，用例只钉文本与数据形状 —— 合并的语义一旦漂移，
读者拿到的就是一篇结构错乱的笔记，而那种问题在端到端里很难定位。
"""

from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.services.note_merge import (
    MergedEntry,
    MergedFailure,
    build_merged_audio_meta,
    build_merged_markdown,
    demote_headings,
    merge_transcripts,
)


def test_demote_headings_shifts_levels_but_keeps_code_fences():
    markdown = "\n".join(
        [
            "# 一级",
            "## 二级",
            "\x60\x60\x60python",
            "# 这是注释，不是标题",
            "\x60\x60\x60",
            "###### 六级",
        ]
    )

    out = demote_headings(markdown)

    assert "## 一级" in out
    assert "### 二级" in out
    # 代码围栏内的 # 原样保留
    assert "# 这是注释，不是标题" in out
    # 六级封顶，不会出现七级
    assert "###### 六级" in out
    assert "####### " not in out


def test_demote_headings_is_a_noop_for_zero_levels():
    markdown = "# 标题\n正文"
    assert demote_headings(markdown, 0) == markdown
    assert demote_headings("", 1) == ""


def test_build_merged_markdown_structure():
    entries = [
        MergedEntry(
            title="第一集",
            markdown="# 视频标题\n## 小节\n正文一",
            duration=65,
            source_url="https://x/1",
        ),
        MergedEntry(title="第二集", markdown="正文二", duration=3725),
    ]
    out = build_merged_markdown(
        "我的合集", entries, [MergedFailure("第三集", "下载失败")]
    )

    assert out.startswith("# 我的合集")
    assert "> 本笔记由 2 个视频的笔记合并而成。" in out
    assert "## 目录" in out
    assert "1. 第一集（1:05）" in out
    assert "2. 第二集（1:02:05）" in out
    assert "## 1. 第一集" in out
    assert "> 来源：https://x/1" in out
    # 正文开头的一级标题被去掉，正文里的二级标题降成三级
    assert "## 视频标题" not in out
    assert "### 小节" in out
    assert "## 2. 第二集" in out
    assert "## 未生成成功的视频" in out
    assert "- 第三集（下载失败）" in out


def test_build_merged_markdown_skips_toc_for_single_entry():
    out = build_merged_markdown(
        "只有一个", [MergedEntry(title="唯一", markdown="正文")]
    )
    assert "## 目录" not in out
    assert "## 1. 唯一" in out


def test_build_merged_markdown_handles_empty_body():
    out = build_merged_markdown("空正文", [MergedEntry(title="空", markdown="")])
    assert "_（这篇笔记没有正文）_" in out


def test_merge_transcripts_inserts_video_dividers():
    first = MergedEntry(
        title="第一集",
        markdown="",
        transcript=TranscriptResult(
            language="zh",
            full_text="第一集全文",
            segments=[TranscriptSegment(0.0, 1.0, "第一集第一句")],
        ),
    )
    second = MergedEntry(
        title="第二集",
        markdown="",
        transcript=TranscriptResult(
            language=None,
            full_text="第二集全文",
            segments=[TranscriptSegment(0.0, 1.0, "第二集第一句")],
        ),
    )

    merged = merge_transcripts([first, second])

    assert merged.language == "zh"
    assert "## 1. 第一集" in merged.full_text
    assert "## 2. 第二集" in merged.full_text
    assert merged.segments[0].text.startswith("—— 第 1 个视频：第一集")
    assert merged.segments[2].text.startswith("—— 第 2 个视频：第二集")


def test_merge_transcripts_tolerates_missing_transcript():
    merged = merge_transcripts([MergedEntry(title="没有转写", markdown="正文")])
    assert merged.full_text == ""
    assert merged.segments == []


def test_build_merged_audio_meta_sums_duration_and_keeps_first_cover():
    entries = [
        MergedEntry(
            title="一",
            markdown="",
            duration=10,
            video_id="BV1_p1",
            cover_url="https://c/1.jpg",
        ),
        MergedEntry(
            title="二", markdown="", duration=32.5, video_id="BV1_p2", cover_url=None
        ),
    ]
    meta = build_merged_audio_meta("合集", entries, video_id="merged_abcd1234")

    assert meta.title == "合集"
    assert meta.duration == 42.5
    assert meta.cover_url == "https://c/1.jpg"
    assert meta.video_id == "merged_abcd1234"
    assert meta.file_path == ""
    assert meta.raw_info == {"merged": True, "merged_from": ["BV1_p1", "BV1_p2"]}
