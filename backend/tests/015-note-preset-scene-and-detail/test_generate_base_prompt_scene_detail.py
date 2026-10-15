"""generate_base_prompt 的拼接顺序与开关行为（spec 015）。"""

from typing import Any

from app.gpt.prompt_builder import generate_base_prompt


def _prompt(**kwargs: Any) -> str:
    # 显式标成 dict[str, Any]：这里的 kwargs 故意是异质的（有 bool、有 list、有 str），
    # 让 pyright 按字面量推断成 dict[str, str] 会把 ocr_assist 之类的开关误判成类型错误。
    all_kwargs: dict[str, Any] = {"title": "标题", "segment_text": "字幕正文", "tags": "标签"}
    all_kwargs.update(kwargs)
    return generate_base_prompt(**all_kwargs)


def test_both_axes_appear_with_scene_before_detail():
    prompt = _prompt(scene="academic", detail="brief")
    assert "**场景：学术**" in prompt
    assert "**篇幅：精简**" in prompt
    assert prompt.index("**场景：学术**") < prompt.index("**篇幅：精简**")


def test_axes_come_after_format_fragments():
    prompt = _prompt(_format=["toc"], scene="life", detail="detailed")
    assert prompt.index("**目录**") < prompt.index("**场景：生活**")
    assert prompt.index("**场景：生活**") < prompt.index("**篇幅：详细**")


def test_extras_still_come_last():
    prompt = _prompt(scene="life", detail="brief", extras="EXTRA-MARKER")
    assert prompt.rstrip().endswith("EXTRA-MARKER")


def test_only_scene_given():
    prompt = _prompt(scene="life")
    assert "**场景：生活**" in prompt
    assert "**篇幅：" not in prompt


def test_only_detail_given():
    prompt = _prompt(detail="detailed")
    assert "**篇幅：详细**" in prompt
    assert "**场景：" not in prompt


def test_neither_axis_given():
    prompt = _prompt()
    assert "**场景：" not in prompt
    assert "**篇幅：" not in prompt


def test_unknown_values_add_nothing():
    prompt = _prompt(scene="xiaohongshu", detail="minimal")
    assert "**场景：" not in prompt
    assert "**篇幅：" not in prompt
