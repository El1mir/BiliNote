"""spec 008 ticket 02：判定契约与插图流程的回归测试。

这个文件存在的首要理由是防「逻辑又做反了」：反转后的契约是
「只有 LLM 判定 worth=true 的候选帧才编入笔记」，一旦有人在某处把
「判定」改回「模型说什么就插什么」，下面的用例必须立刻红。
"""
import json

import pytest

from app.services.ocr_assist import (
    MAX_NOTE_IMAGES,
    JudgementOutcome,
    WorthDecision,
    WorthJudgementError,
    build_candidate_index,
    build_candidates_text,
    build_judge_system_prompt,
    format_mmss,
    parse_worth_judgement,
    render_shot_table,
)

CANDIDATES = [10.0, 20.0, 30.0, 125.0, 3600.0]


def judge(frames, candidates=None, max_images=MAX_NOTE_IMAGES):
    text = json.dumps({"frames": frames}, ensure_ascii=False)
    return parse_worth_judgement(text, CANDIDATES if candidates is None else candidates, max_images)


# --------------------------------------------------------------------------
# format_mmss
# --------------------------------------------------------------------------
def test_format_mmss_basic():
    assert format_mmss(0) == "00:00"
    assert format_mmss(12) == "00:12"
    assert format_mmss(125) == "02:05"
    assert format_mmss(3599) == "59:59"


def test_format_mmss_handles_beyond_99_minutes():
    """这正是不能沿用 *Screenshot-[mm:ss] 标记的原因：正则的 \\d{2} 表达不了三位分钟。"""
    assert format_mmss(3600) == "1:00:00"
    assert format_mmss(6005) == "1:40:05"
    assert format_mmss(600000) == "166:40:00"


def test_format_mmss_is_tolerant_of_garbage():
    assert format_mmss(None) == "00:00"
    assert format_mmss("abc") == "00:00"
    assert format_mmss(-5) == "00:00"


# --------------------------------------------------------------------------
# 候选清单对齐
# --------------------------------------------------------------------------
def test_build_candidate_index_keys_on_whole_seconds():
    """候选点按「最近的整秒」取键：20.4 → 20，20.9 → 21（抽帧本身就是秒级精度）。"""
    index = build_candidate_index([10.0, 20.4, 20.9, 30])
    assert index == {10: 10.0, 20: 20.4, 21: 20.9, 30: 30.0}
    # 落在同一个整秒上的重复候选只保留第一个
    assert build_candidate_index([20.4, 20.49]) == {20: 20.4}


def test_build_candidate_index_ignores_garbage():
    assert build_candidate_index([None, "abc", -1, 5]) == {5: 5}


# --------------------------------------------------------------------------
# parse_worth_judgement：核心契约
# --------------------------------------------------------------------------
def test_only_worth_true_is_approved():
    outcome = judge(
        [
            {"time": 10.0, "worth": True, "reason": "有公式", "caption": "求根公式"},
            {"time": 20.0, "worth": False, "reason": "只是人脸"},
            {"time": 30.0, "worth": True, "reason": "有几何图"},
        ]
    )
    assert [d.time for d in outcome.approved] == [10.0, 30.0]
    assert outcome.approved[0].caption == "求根公式"
    assert outcome.approved[0].reason == "有公式"
    assert outcome.worth_true == 2
    assert outcome.worth_false == 1
    assert outcome.total == 3


def test_time_not_in_candidates_is_discarded():
    """模型自己编一个时间点绝不能导致抽帧——否则「只有判定的帧才插图」就被绕过了。"""
    outcome = judge([{"time": 999.0, "worth": True}])
    assert outcome.approved == []
    assert outcome.rejected_out_of_candidates == 1
    assert outcome.worth_true == 1


def test_approved_time_snaps_to_the_candidate_value():
    """模型写 20.4 也要落到候选点 20.0 上（抽帧是秒级精度）。"""
    outcome = judge([{"time": 20.4, "worth": True}])
    assert [d.time for d in outcome.approved] == [20.0]


def test_duplicate_approved_times_collapse():
    outcome = judge([{"time": 10.0, "worth": True}, {"time": 10.0, "worth": True}])
    assert [d.time for d in outcome.approved] == [10.0]
    assert outcome.rejected_duplicate == 1


def test_entries_with_missing_fields_are_counted_as_invalid():
    outcome = judge([{"time": 10.0}, {"worth": True}, "不是对象", {"time": "x", "worth": True}])
    assert outcome.approved == []
    assert outcome.rejected_invalid == 4


def test_worth_accepts_string_forms():
    outcome = judge([{"time": 10.0, "worth": "true"}, {"time": 20.0, "worth": "false"}])
    assert [d.time for d in outcome.approved] == [10.0]
    assert outcome.worth_false == 1


def test_time_accepts_timecode_strings():
    outcome = judge([{"time": "00:10", "worth": True}, {"time": "02:05", "worth": True}])
    assert [d.time for d in outcome.approved] == [10.0, 125.0]


def test_cap_truncates_and_counts():
    candidates = list(range(0, 20))
    frames = [{"time": float(t), "worth": True} for t in candidates]
    outcome = parse_worth_judgement(json.dumps({"frames": frames}), candidates, max_images=3)
    assert len(outcome.approved) == 3
    assert outcome.dropped_by_cap == 17
    assert [d.time for d in outcome.approved] == [0.0, 1.0, 2.0]


def test_approved_is_sorted_by_time():
    outcome = judge([{"time": 30.0, "worth": True}, {"time": 10.0, "worth": True}])
    assert [d.time for d in outcome.approved] == [10.0, 30.0]


# --------------------------------------------------------------------------
# 「模型说没有」与「解析失败」都降级（spec 022 D6 取代 spec 008 §5.6b）
# --------------------------------------------------------------------------
def test_empty_frames_degrades_to_all_candidates():
    """spec 022 D6：显式空清单不再表示「不插图」。

    空清单与「模型什么都没说清楚」在输出上无法区分，一篇文章因为一次空回复
    丢掉全部插图，比多留几张图更糟。降级原因记 empty_frames，上层写进 detail。
    """
    outcome = judge([])
    assert outcome.degraded == "empty_frames"
    assert [d.time for d in outcome.approved] == CANDIDATES
    assert outcome.total == len(CANDIDATES)
    assert outcome.worth_false == 0


def test_unparseable_output_raises_instead_of_silently_returning_empty():
    """一次网络抖动不能让整篇笔记悄悄变成没有插图的笔记。"""
    for garbage in ["", "   ", "抱歉，我无法完成这个请求。", "{" ]:
        with pytest.raises(WorthJudgementError):
            parse_worth_judgement(garbage, CANDIDATES)


def test_bare_list_output_is_accepted():
    outcome = parse_worth_judgement(json.dumps([{"time": 10.0, "worth": True}]), CANDIDATES)
    assert [d.time for d in outcome.approved] == [10.0]


def test_code_fenced_output_is_accepted():
    text = '```json\n{"frames": [{"time": 10.0, "worth": true}]}\n```'
    outcome = parse_worth_judgement(text, CANDIDATES)
    assert [d.time for d in outcome.approved] == [10.0]


def test_output_with_surrounding_prose_is_accepted():
    text = '好的，我的判定如下：\n{"frames": [{"time": 30.0, "worth": true}]}\n希望有帮助。'
    outcome = parse_worth_judgement(text, CANDIDATES)
    assert [d.time for d in outcome.approved] == [30.0]


def test_dict_without_a_frame_list_raises():
    with pytest.raises(WorthJudgementError):
        parse_worth_judgement('{"result": "ok"}', CANDIDATES)


def test_single_object_output_is_treated_as_one_entry():
    outcome = parse_worth_judgement('{"time": 10.0, "worth": true}', CANDIDATES)
    assert [d.time for d in outcome.approved] == [10.0]


# --------------------------------------------------------------------------
# 提示词与对照表
# --------------------------------------------------------------------------
def test_judge_prompt_has_no_unreplaced_placeholders():
    prompt = build_judge_system_prompt(CANDIDATES, duration=4000, max_items=7)
    assert "{TOTAL}" not in prompt
    assert "{DURATION}" not in prompt
    assert "{CANDIDATES}" not in prompt
    assert "{MAX_ITEMS}" not in prompt
    assert "共 5 个" in prompt
    assert "视频总长 4000 秒" in prompt
    assert "最多只能有 7 个" in prompt
    # JSON 示例里的花括号必须保留成合法 JSON 的样子
    assert '{"frames":[{"time":123.4,"worth":true' in prompt


def test_judge_prompt_lists_every_candidate():
    prompt = build_judge_system_prompt(CANDIDATES)
    for seconds in CANDIDATES:
        assert f"- {seconds} " in prompt


def test_candidates_text_handles_empty_list():
    assert build_candidates_text([]) == "- （没有候选画面）"


def test_shot_table_numbers_from_one_and_carries_caption():
    table = render_shot_table(
        [
            WorthDecision(time=10.0, caption="求根公式"),
            WorthDecision(time=125.0, reason="没有 caption 时用 reason"),
        ]
    )
    assert "`[[SHOT-1]]` → 00:10（求根公式）" in table
    assert "`[[SHOT-2]]` → 02:05（没有 caption 时用 reason）" in table


def test_outcome_describe_is_human_readable():
    outcome = judge([{"time": 10.0, "worth": True}, {"time": 999.0, "worth": True}])
    text = outcome.describe()
    assert "最终通过=1" in text
    assert "丢弃(不在候选清单)=1" in text


def test_outcome_default_is_empty():
    outcome = JudgementOutcome()
    assert outcome.approved == []
    assert outcome.describe()
