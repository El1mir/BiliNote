"""前后端词表同步（spec 015）。

后端只保留提示词，取值清单的**来源**是前端常量。所以这份测试是唯一一处把两侧钉在
一起的地方：任何一侧单方面改词表，这里就会红。

顺序也要一致 —— 常量数组的顺序就是下拉框里的展示顺序。
"""

import re
from pathlib import Path

import pytest

from app.gpt.prompt_builder import DETAIL_PROMPTS, SCENE_PROMPTS

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_NOTE_TS = ROOT / "BillNote_frontend" / "src" / "constant" / "note.ts"
EXTENSION_TYPES_TS = ROOT / "BillNote_extension" / "src" / "logic" / "types.ts"

#: 两个源文件的读取形状不同，但取值都写成 `value: 'xxx'`。
_VALUE_RE = re.compile(r"value:\s*'([A-Za-z_]+)'")

needs_frontend = pytest.mark.skipif(
    not FRONTEND_NOTE_TS.is_file(), reason="前端不在当前 checkout（后端单独检出时不阻塞）"
)
needs_extension = pytest.mark.skipif(
    not EXTENSION_TYPES_TS.is_file(), reason="浏览器扩展不在当前 checkout（后端单独检出时不阻塞）"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _values(source: str, marker: str, terminator: str = "]") -> list[str]:
    start = source.index(marker)
    end = source.index(terminator, start)
    return _VALUE_RE.findall(source[start:end])


def _union_members(source: str, name: str) -> list[str]:
    match = re.search(rf"export type {name} = ([^\n]+)", source)
    assert match is not None, f"没找到 {name} 的类型定义"
    return re.findall(r"'([A-Za-z_]+)'", match.group(1))


@needs_frontend
def test_web_scene_vocabulary_matches_backend():
    assert _values(_read(FRONTEND_NOTE_TS), "noteScenes = [") == list(SCENE_PROMPTS)


@needs_frontend
def test_web_detail_vocabulary_matches_backend():
    assert _values(_read(FRONTEND_NOTE_TS), "noteDetails = [") == list(DETAIL_PROMPTS)


@needs_extension
def test_extension_scene_vocabulary_matches_backend():
    source = _read(EXTENSION_TYPES_TS)
    assert _values(source, "NOTE_SCENES") == list(SCENE_PROMPTS)
    assert _union_members(source, "NoteScene") == list(SCENE_PROMPTS)


@needs_extension
def test_extension_detail_vocabulary_matches_backend():
    source = _read(EXTENSION_TYPES_TS)
    assert _values(source, "NOTE_DETAILS") == list(DETAIL_PROMPTS)
    assert _union_members(source, "NoteDetail") == list(DETAIL_PROMPTS)


@needs_frontend
def test_web_drops_the_old_style_list():
    source = _read(FRONTEND_NOTE_TS)
    assert "noteStyles" not in source
    for legacy in ("xiaohongshu", "life_journal", "task_oriented", "meeting_minutes", "minimal"):
        assert legacy not in source, legacy


@needs_extension
def test_extension_drops_the_old_style_list():
    source = _read(EXTENSION_TYPES_TS)
    assert "NOTE_STYLES" not in source
    assert "NoteStyle" not in source
    for legacy in ("xiaohongshu", "life_journal", "task_oriented", "meeting_minutes", "minimal"):
        assert legacy not in source, legacy
