"""BASE_PROMPT 与「按勾选追加」的片段之间的契约（spec 015 增补）。

为什么要有这个文件：BASE_PROMPT 是唯一一份不走场景/详略拼装的恒定文本，四家消费者
（prompt_builder、openai_gpt、qwen_gpt、deepseek_gpt）都拿它做 str.format。它也是最容易
被改坏的地方——文案里多一个花括号，四家会一起抛 KeyError。
"""

import re
import string

import pytest

from app.gpt import prompt_builder
from app.gpt.prompt import AI_SUM, BASE_PROMPT, LINK, SCREENSHOT
from app.gpt.prompt_builder import DETAIL_PROMPTS, SCENE_PROMPTS

#: 「按勾选追加」的片段一律不写行首编号：它们一次只追加一条，编号既会让模型看到一个
#: 孤立的「7.」，也无法保证连续（没勾目录时就会 8. 9. 10. 直接跳号）。
LINE_NUMBERING = re.compile(r"^\s*\d+\.\s", re.M)

#: BASE_PROMPT 只允许这三个占位符。
EXPECTED_FIELDS = {"video_title", "tags", "segment_text"}


def test_base_prompt_only_uses_the_three_format_fields():
    """解析出文案里真正的占位符，多一个都不放过。

    典型踩坑：文案里直接写 LaTeX 分数（反斜杠 frac 那种），花括号会被当成占位符，
    四家消费者同时抛 KeyError。
    """
    fields = {name for _, name, _, _ in string.Formatter().parse(BASE_PROMPT) if name}
    assert fields == EXPECTED_FIELDS


def test_base_prompt_formats_without_error():
    out = BASE_PROMPT.format(video_title="TITLE-X", tags="TAGS-X", segment_text="SEG-X")
    assert "TITLE-X" in out and "TAGS-X" in out and "SEG-X" in out


def test_base_prompt_defers_to_the_length_directive():
    """回归：spec 015 之前 BASE_PROMPT 写死「宁可长一些也不要漏掉内容」，
    与新增的「篇幅：精简」直接对立——同一份提示词里两句话互相拉扯。
    """
    assert "以篇幅指示为准" in BASE_PROMPT


def test_base_prompt_reconciles_brief_with_keep_everything():
    """「精简」必须被定义成压缩表达而不是删内容——这是两段文案能共存的前提。"""
    assert "不再逐段展开" in BASE_PROMPT
    assert "不是删内容" in BASE_PROMPT


def test_base_prompt_declares_which_side_wins():
    assert "优先于上面的通用原则" in BASE_PROMPT
    assert "以任务里的指示为准" in BASE_PROMPT


def test_base_prompt_fixes_the_heading_convention():
    """目录与「原片跳转」两个 format 都假定章节是 ## 标题，
    但四个格式开关全关掉时，原来的提示词从没交代过标题层级。
    """
    assert "`## ` 标题" in BASE_PROMPT
    assert "`### ` 标题" in BASE_PROMPT


def _appended_fragments(monkeypatch):
    """所有「按用户勾选、一次只追加一条」的片段。"""
    monkeypatch.setattr(
        "app.services.ocr_assist.render_shot_table",
        lambda shots: "| 编号 | 时间 | 说明 |",
    )
    fragments = {
        "toc": prompt_builder.get_toc_format(),
        "link": prompt_builder.get_link_format(),
        "screenshot": prompt_builder.get_screenshot_format(),
        "summary": prompt_builder.get_summary_format(),
        "ocr_screenshot_empty": prompt_builder.get_ocr_assist_screenshot_format([]),
        "ocr_screenshot_filled": prompt_builder.get_ocr_assist_screenshot_format(
            [{"index": 1, "timestamp": "00:10", "reason": "r"}]
        ),
        "LINK": LINK,
        "SCREENSHOT": SCREENSHOT,
        "AI_SUM": AI_SUM,
    }
    for scene, fragment in SCENE_PROMPTS.items():
        fragments["scene:" + scene] = fragment
    for detail, fragment in DETAIL_PROMPTS.items():
        fragments["detail:" + detail] = fragment
    return fragments


def test_appended_fragments_carry_no_line_numbering(monkeypatch):
    """编号只留给 BASE_PROMPT 里那六条恒定原则；追加片段一律不带。"""
    for name, fragment in _appended_fragments(monkeypatch).items():
        assert LINE_NUMBERING.findall(fragment) == [], name


def test_appended_fragments_are_not_empty(monkeypatch):
    for name, fragment in _appended_fragments(monkeypatch).items():
        assert fragment.strip(), name


@pytest.mark.parametrize("scene", sorted(SCENE_PROMPTS))
def test_scene_fragment_is_present_in_the_assembled_prompt(scene):
    prompt = prompt_builder.generate_base_prompt(
        "标题", "字幕正文", "标签", scene=scene, detail="brief"
    )
    assert SCENE_PROMPTS[scene] in prompt
    assert DETAIL_PROMPTS["brief"] in prompt
