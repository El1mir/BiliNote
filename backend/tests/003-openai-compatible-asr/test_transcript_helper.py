"""spec 003 追加：只返回文字的 ASR（MiMo chat 风格）的时间轴插值。"""
from app.models.transcriber_model import TranscriptSegment
from app.utils.transcript_helper import densify_segments, split_text_into_pieces


def test_split_text_by_sentence_punctuation():
    pieces = split_text_into_pieces("第一句。第二句！第三句？")
    assert pieces == ["第一句。", "第二句！", "第三句？"]


def test_split_long_sentence_by_length():
    pieces = split_text_into_pieces("啊" * 150, max_chars=60)
    assert [len(p) for p in pieces] == [60, 60, 30]


def test_densify_single_huge_segment_interpolates_timeline():
    # 模拟 MiMo chat 风格：整段 600s 只有一段文字
    text = "。".join(f"第{i}句话内容" for i in range(30)) + "。"
    segments = [TranscriptSegment(start=0.0, end=600.0, text=text)]

    out = densify_segments(segments)

    assert len(out) == 30
    assert out[0].start == 0.0
    assert out[-1].end == 600.0
    # 时间轴单调递增，且都落在原段范围内
    starts = [s.start for s in out]
    assert starts == sorted(starts)
    assert all(0.0 <= s.start <= s.end <= 600.0 for s in out)


def test_densify_keeps_normal_short_segments_untouched():
    segments = [
        TranscriptSegment(start=0.0, end=3.0, text="第一句"),
        TranscriptSegment(start=3.0, end=6.0, text="第二句"),
    ]
    out = densify_segments(segments)
    assert out == segments


def test_densify_handles_empty_and_textless():
    assert densify_segments([]) == []
    seg = TranscriptSegment(start=0.0, end=600.0, text="")
    assert densify_segments([seg]) == [seg]


def test_densify_caps_segment_count():
    text = "。".join("一句话" for _ in range(2000)) + "。"
    segments = [TranscriptSegment(start=0.0, end=3600.0, text=text)]
    out = densify_segments(segments, max_segments=100)
    assert len(out) == 100
