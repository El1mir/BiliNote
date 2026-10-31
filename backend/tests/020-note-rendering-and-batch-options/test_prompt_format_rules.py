"""提示词里对公式格式与画面内容的约束（spec 020）。

为什么要钉：读者端是 remark-math + KaTeX，模型只要把块公式写成
`$$...$$` 挤在一行，整篇笔记就会退化成文本 + 满屏红色报错；画面里的题目
被「总结成一句话」也等于把原始材料丢了。两条都是**提示词侧**的契约。
"""

import string

from app.gpt.prompt import BASE_PROMPT


def _fields() -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(BASE_PROMPT) if name}


def test_formula_rules_are_explicit():
    """行内只认 `$...$`、块公式的 `$$` 必须单独占一行。"""
    assert "行内公式只写" in BASE_PROMPT
    assert "**必须单独占一行**" in BASE_PROMPT
    assert "不要写成" in BASE_PROMPT


def test_formula_rules_forbid_latex_delimiters():
    """模型很爱写 \\(...\\) / \\[...\\]，读者端不认这两个分隔符。"""
    assert "\\(...\\)" in BASE_PROMPT
    assert "\\[...\\]" in BASE_PROMPT
    assert "不要写" in BASE_PROMPT

def test_image_content_is_preserved_verbatim():
    """画面里的题目原样保留：不改写、不讲解、不总结。"""
    assert "原样保留" in BASE_PROMPT
    assert "不要改写" in BASE_PROMPT
    assert "不要替读者总结" in BASE_PROMPT
    assert "保留截图" in BASE_PROMPT


def test_prompt_still_formats_with_three_fields():
    """加了新文案也不能多出占位符（花括号会被 str.format 当字段）。"""
    assert _fields() == {"video_title", "tags", "segment_text"}
    out = BASE_PROMPT.format(video_title="T", tags="G", segment_text="S")
    assert "T" in out and "G" in out and "S" in out
