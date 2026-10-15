"""场景 / 详略片段本身的契约（spec 015）。"""

import re

from app.gpt.prompt_builder import (
    DETAIL_PROMPTS,
    SCENE_PROMPTS,
    get_detail_prompt,
    get_scene_prompt,
)

#: 旧版把九个风格拼进同一份提示词时留下的行首编号（如 `7. **商业风格**`）。
LINE_NUMBERING = re.compile(r"^\s*\d+\.\s", re.M)

#: format 片段占用的编号（get_toc_format / get_link_format / ...）。
FORMAT_NUMBERING = {"9.", "10.", "11.", "12."}


def test_every_scene_returns_a_non_empty_prompt():
    for scene in SCENE_PROMPTS:
        assert get_scene_prompt(scene).strip(), scene


def test_every_detail_returns_a_non_empty_prompt():
    for detail in DETAIL_PROMPTS:
        assert get_detail_prompt(detail).strip(), detail


def test_prompts_within_an_axis_are_distinct():
    scenes = [get_scene_prompt(s) for s in SCENE_PROMPTS]
    details = [get_detail_prompt(d) for d in DETAIL_PROMPTS]
    assert len(set(scenes)) == len(scenes)
    assert len(set(details)) == len(details)


def test_every_scene_names_its_reader():
    """场景这一维的职责就是交代「读者是谁、他拿这份笔记做什么」。"""
    for scene, fragment in SCENE_PROMPTS.items():
        assert "读者" in fragment, scene


def test_unknown_and_missing_values_return_empty_string():
    assert get_scene_prompt("nope") == ""
    assert get_scene_prompt(None) == ""
    assert get_scene_prompt("") == ""
    assert get_detail_prompt("nope") == ""
    assert get_detail_prompt(None) == ""
    assert get_detail_prompt("") == ""
    # 旧取值不再被识别（spec 015 决策 4：不做老任务兼容）
    assert get_scene_prompt("xiaohongshu") == ""
    assert get_detail_prompt("minimal") == ""


def test_fragments_carry_no_line_numbering():
    """回归 spec 015 §背景问题 3：编号是九个风格被拼在一起时的残留。"""
    combined = "\n".join([*SCENE_PROMPTS.values(), *DETAIL_PROMPTS.values()])
    assert LINE_NUMBERING.findall(combined) == []


def test_fragments_do_not_collide_with_format_numbering():
    for fragment in [*SCENE_PROMPTS.values(), *DETAIL_PROMPTS.values()]:
        for line in fragment.splitlines():
            assert line.split(" ", 1)[0] not in FORMAT_NUMBERING


def test_vocabulary_is_exactly_the_agreed_sets():
    assert set(SCENE_PROMPTS) == {"life", "academic", "professional"}
    assert set(DETAIL_PROMPTS) == {"brief", "detailed"}
