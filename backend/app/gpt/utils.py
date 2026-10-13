import codecs
import json
import re
from typing import Any


def fix_markdown(markdown: str) -> str:
    return codecs.decode(markdown, 'unicode_escape')


def load_llm_json(text: str) -> Any:
    """从模型输出里尽力捞出 JSON 对象或数组，捞不到返回 ``None``。

    容错顺序与 `universal_gpt.parse_frame_plan` 原本的内联实现一致：
    去掉 markdown 代码块包裹 → 整体 ``json.loads`` → 失败则正则捞第一个
    ``{...}`` / ``[...]`` 再解析。

    提炼成公共函数是为了让 spec 008 的「判定契约」复用同一套容错：
    两处各写一遍必然会逐渐分叉，而分叉后的表现是「某一类模型输出在 A 功能能解析、
    在 B 功能解析不了」这种极难排查的差异。

    :param text: 模型返回的原始文本
    :return: 解析出的 dict / list；无法解析时为 None
    """
    raw = (text or "").strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()

    try:
        return json.loads(raw)
    except Exception:
        pass

    match = re.search(r"\{.*\}|\[.*\]", raw, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None
