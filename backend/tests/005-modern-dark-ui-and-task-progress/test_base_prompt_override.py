"""BASE_PROMPT 覆盖层的归一化 / 保存 / 生效链路（spec 005 ticket 11）。

为什么单独钉这一个字段：它和其余设置项的语义**不同**。其余字段的「没设置」用
None 表达、有各自的合法下界；覆盖层用**空串**表达「用内置模板」，而空串恰恰是
用户点「恢复默认」时唯一能传的东西。任何一处把空串当成「没传」，恢复默认就会
静默失效 —— 所以下面四条链路要逐个测：

1. normalize_base_prompt_override 的收敛规则（空 / 缺占位符 / 超长 -> 空串）；
2. 写路径：空串能真的存进去，不被「is not None 才算传了」挡掉；
3. 读路径：runtime_limits.base_prompt_override() 反映数据库里的值；
4. 生效路径：resolve_base_prompt() 被所有消费者共用，改了设置页就改到下一次
   生成用的模板。

**不碰真实数据库**：把 DAO 的 get_db 换成指向 tmp_path 里临时 SQLite 的会话。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import general_settings_dao as dao
from app.db.engine import Base
from app.db.models.general_settings import (
    MAX_BASE_PROMPT_OVERRIDE_CHARS,
    REQUIRED_PROMPT_PLACEHOLDERS,
)
from app.gpt.prompt import BASE_PROMPT
from app.gpt.prompt_builder import generate_base_prompt, resolve_base_prompt
from app.services import runtime_limits

VALID_TEMPLATE = "标题：{video_title}\n字幕：{segment_text}\n标签：{tags}\n请据此写笔记。"


@pytest.fixture
def dao_env(tmp_path, monkeypatch):
    """把 DAO 的 get_db 换成临时 SQLite 的会话工厂，并清掉运行时缓存。"""
    db_engine = create_engine(
        f"sqlite:///{tmp_path / 'prompt-override.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(db_engine)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)

    def _fake_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dao, "get_db", _fake_get_db)
    monkeypatch.delenv("BASE_PROMPT_OVERRIDE", raising=False)
    runtime_limits.reset_cache()
    yield factory
    runtime_limits.reset_cache()


# --- 1. 归一化：三条硬规则 ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   \n\t ", ""),  # 只有空白 = 没覆盖
        ("没有占位符的模板", ""),  # 缺占位符 -> 判无效，绝不静默生成无正文笔记
        ("{video_title} 只有标题 {segment_text}", ""),  # 少一个也不行
        ("x" * (MAX_BASE_PROMPT_OVERRIDE_CHARS + 1)
         + "".join("{" + name + "}" for name in REQUIRED_PROMPT_PLACEHOLDERS), ""),  # 超长 -> 拒绝而非截断
        ("  " + VALID_TEMPLATE + "  ", VALID_TEMPLATE),  # 合法模板会被 strip
    ],
)
def test_normalize_rules(raw, expected):
    assert dao.normalize_base_prompt_override(raw) == expected


def test_normalize_keeps_all_required_placeholders():
    """占位符集合来自模型常量，模板一旦缺任何一个都必须判无效。"""
    assert set(REQUIRED_PROMPT_PLACEHOLDERS) == {"video_title", "segment_text", "tags"}
    for name in REQUIRED_PROMPT_PLACEHOLDERS:
        template = VALID_TEMPLATE.replace("{" + name + "}", "")
        assert dao.normalize_base_prompt_override(template) == ""


# --- 2. 写路径：空串要真的存进去 ---------------------------------------------


def test_update_saves_override_and_can_clear_it(dao_env):
    saved = dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    assert saved["base_prompt_override"] == VALID_TEMPLATE
    assert dao.get_general_settings()["base_prompt_override"] == VALID_TEMPLATE

    # 空串 = 恢复默认。这一条最容易被「is not None 才算传了」的逻辑吃掉。
    cleared = dao.update_general_settings(base_prompt_override="")
    assert cleared["base_prompt_override"] == ""
    assert dao.get_general_settings()["base_prompt_override"] == ""


def test_update_ignores_when_field_not_passed(dao_env):
    """没传这个字段时保持原值，不能被顺手清空。"""
    dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    dao.update_general_settings(max_parallel_notes=2)
    assert dao.get_general_settings()["base_prompt_override"] == VALID_TEMPLATE


def test_invalid_template_is_rejected_not_saved(dao_env):
    dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    dao.update_general_settings(base_prompt_override="没有占位符")
    assert dao.get_general_settings()["base_prompt_override"] == ""


def test_serialize_exposes_default_and_limits(dao_env):
    """设置页不抄常量：默认模板、上限、必需占位符都随设置一起下发。"""
    payload = dao.get_general_settings()
    assert payload["base_prompt_default"] == BASE_PROMPT
    assert payload["base_prompt_override_limit"] == MAX_BASE_PROMPT_OVERRIDE_CHARS
    assert list(payload["base_prompt_required_placeholders"]) == list(
        REQUIRED_PROMPT_PLACEHOLDERS
    )


# --- 3+4. 读路径与生效路径 ---------------------------------------------------


def test_resolve_falls_back_to_builtin_when_empty(dao_env):
    assert runtime_limits.base_prompt_override() == ""
    assert resolve_base_prompt() == BASE_PROMPT


def test_resolve_returns_override_after_save(dao_env):
    dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    # 写路径会 reset_cache()，所以下一个任务就能看到新模板，不需要重启。
    runtime_limits.reset_cache()
    assert runtime_limits.base_prompt_override() == VALID_TEMPLATE
    assert resolve_base_prompt() == VALID_TEMPLATE


def test_generate_base_prompt_uses_override(dao_env):
    """端到端：设置页保存 -> 下一次生成用的就是新模板。"""
    dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    runtime_limits.reset_cache()

    prompt = generate_base_prompt("我的标题", "第一段字幕", ["标签A"])
    assert prompt.startswith("标题：我的标题")
    assert "第一段字幕" in prompt
    assert "标签A" in prompt
    # 内置模板的特征句不该再出现 —— 否则说明覆盖层没生效。
    assert _builtin_fingerprint() not in prompt


def test_generate_base_prompt_is_unchanged_without_override(dao_env):
    prompt = generate_base_prompt("我的标题", "第一段字幕", ["标签A"])
    # 没有覆盖层时输出必须与「内置模板直接 format」逐字节一致。
    expected = BASE_PROMPT.format(
        video_title="我的标题", segment_text="第一段字幕", tags=["标签A"]
    )
    assert prompt.startswith(expected)
    assert _builtin_fingerprint() in prompt


def _builtin_fingerprint() -> str:
    """内置模板里一段稳定的特征文字（首行是空行，不能直接取 [0]）。"""
    for line in BASE_PROMPT.splitlines():
        cleaned = line.strip()
        if len(cleaned) >= 10:
            return cleaned[:10]
    raise AssertionError("BASE_PROMPT 里找不到足够长的特征行")


def test_env_var_wins_over_database(dao_env, monkeypatch):
    """部署方用 env 固定模板时，界面上的手滑不该改掉它（与其余字段一致）。"""
    dao.update_general_settings(base_prompt_override=VALID_TEMPLATE)
    runtime_limits.reset_cache()
    monkeypatch.setenv("BASE_PROMPT_OVERRIDE", "env 模板 {video_title}{segment_text}{tags}")
    assert resolve_base_prompt() == "env 模板 {video_title}{segment_text}{tags}"


def test_legacy_adapters_share_the_resolver():
    """三个旧适配器必须走 resolve_base_prompt，不能各自拿模块级常量 format。

    这三处是 2026-10-05 复核时发现的第四处落点：只改 prompt_builder 的话，走
    deepseek / openai / qwen 的生成依然用旧模板。
    """
    import inspect

    from app.gpt import deepseek_gpt, openai_gpt, qwen_gpt

    for module in (deepseek_gpt, openai_gpt, qwen_gpt):
        source = inspect.getsource(module)
        assert "resolve_base_prompt().format(" in source, module.__name__
        assert "BASE_PROMPT.format(" not in source, module.__name__
