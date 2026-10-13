"""回归：挑选层不得再交白卷（模型返回空数组时必须均匀覆盖兜底）。

背景（真实事故）：``BV147411K7xu?p=198`` 只有 7 段语音识别乱码字幕，模型按旧
提示词的逃生口原样返回 ``{"frames":[]}``，而 ``_pick_note_frames`` 把空结果当
硬异常，整条任务三次重试全废。这里的用例把那条路径钉死：

1. 提示词必须给出数量下限，且不再把「返回空数组」写成常规选项；
2. 模型真返回空数组时，``plan_frame_timestamps`` 必须自己补出均匀覆盖；
3. 时长未知时用字幕末尾时间兜底，仍然不许返回空。
"""
from types import SimpleNamespace

from app.gpt.universal_gpt import (
    PLAN_COVERAGE_SECONDS,
    UniversalGPT,
    build_frame_plan_prompt,
    plan_min_items,
    uniform_frame_plan,
)
from app.models.transcriber_model import TranscriptSegment


def _gpt_returning(content: str):
    captured = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=content)
                )]
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions)

    return UniversalGPT(client=FakeClient(), model="m"), captured


def test_plan_prompt_demands_a_minimum_and_keeps_json_braces():
    prompt = build_frame_plan_prompt(duration=600.0, max_items=200)

    assert "{MIN_ITEMS}" not in prompt
    assert "{MAX_GAP}" not in prompt
    assert "{DURATION_RANGE}" not in prompt
    # 花括号仍是合法 JSON 示例（不能走 str.format）
    assert '{"frames": [{"time": 123.4' in prompt
    # 600 秒 / 30 秒 = 20 项下限
    assert "至少 20 项" in prompt
    assert "不要超过 30 秒" in prompt
    assert "且在 0 ~ 600.0 之间" in prompt


def test_plan_prompt_never_offers_an_empty_array_as_the_usual_answer():
    prompt = build_frame_plan_prompt(duration=600.0, max_items=200)

    # 逃生口必须带上前提条件，且明确「不是」交白卷的理由
    assert "这**不是**「没有值得截图的地方」的理由" in prompt
    assert "只有整段视频确实没有任何画面内容" in prompt


def test_plan_min_items_is_never_zero():
    assert plan_min_items(duration=0.0, max_items=200) == 3
    assert plan_min_items(duration=77.1, max_items=200) == 3
    assert plan_min_items(duration=600.0, max_items=200) == 20
    # 下限永远不超过上限
    assert plan_min_items(duration=100000.0, max_items=5) == 5


def test_uniform_frame_plan_covers_the_whole_video():
    plan = uniform_frame_plan(duration=600.0, max_items=200)

    assert len(plan) == 20
    assert plan == sorted(plan)
    assert plan[0] > 0 and plan[-1] < 600.0
    # 相邻间隔都在覆盖密度以内
    gaps = [b - a for a, b in zip(plan, plan[1:])]
    assert max(gaps) <= PLAN_COVERAGE_SECONDS * 2


def test_uniform_frame_plan_without_duration_returns_nothing():
    assert uniform_frame_plan(duration=0.0, max_items=200) == []


def test_empty_model_answer_falls_back_to_uniform_coverage():
    """核心回归：模型返回 {"frames":[]} 时不许再把空结果交给调用方。"""
    gpt, captured = _gpt_returning('{"frames":[]}')

    picks = gpt.plan_frame_timestamps(
        [TranscriptSegment(0.0, 3.0, "乱码")], duration=77.1, max_items=200
    )

    assert picks, "模型交白卷时必须兜底，否则 OCR 辅助模式整条任务失败"
    assert picks == sorted(picks)
    # 提示词里的下限也被替换掉了
    assert "{MIN_ITEMS}" not in captured["messages"][0]["content"]


def test_empty_model_answer_without_duration_uses_subtitle_end():
    """时长探测失败时用字幕末尾兜底，仍然不许返回空。"""
    gpt, captured = _gpt_returning('{"frames":[]}')

    picks = gpt.plan_frame_timestamps(
        [
            TranscriptSegment(0.0, 30.0, "a"),
            TranscriptSegment(30.0, 120.0, "b"),
        ],
        duration=0.0,
        max_items=200,
    )

    assert picks
    assert all(0 <= t <= 120.0 for t in picks)
    assert "{DURATION_RANGE}" not in captured["messages"][0]["content"]


def test_model_answer_wins_over_the_fallback():
    gpt, _ = _gpt_returning('{"frames":[{"time":5.0},{"time":9.0}]}')

    picks = gpt.plan_frame_timestamps(
        [TranscriptSegment(0.0, 3.0, "你好")], duration=100.0, max_items=200
    )

    assert picks == [5.0, 9.0]
