"""第一人称与补充内容契约（spec 017，2026-10-18 增补）。

为什么要有这个文件：用户反馈旧提示词把课程笔记写成了第三人称摘要，
并且「课内没讲、但理解必需」的内容与课内内容混在一起无法区分。
现在这两条都是硬约束：全篇讲课人第一人称；补充内容一律以 `> 补充：` 开头。
约束一旦被改文案时悄悄删掉，模型不会报错，只会默默退回旧行为——所以锁在测试里。
"""

from app.gpt.prompt import BASE_PROMPT, MERGE_PROMPT
from app.gpt.prompt_builder import DETAIL_PROMPTS, SCENE_PROMPTS, generate_base_prompt

#: 补充内容的唯一标记：Markdown 引用块，前端 blockquote 有独立样式。
SUPPLEMENT_MARKER = "`> 补充：`"


def test_base_prompt_declares_first_person_narrator():
    """整份提示词的口径：讲课人本人第一人称，不是第三方摘要。"""
    assert "第一人称" in BASE_PROMPT
    assert "讲课人" in BASE_PROMPT
    assert "我" in BASE_PROMPT and "我们" in BASE_PROMPT


def test_base_prompt_forbids_third_person_framing():
    """「视频中提到」「作者介绍了」是旧行为最典型的症状。"""
    assert "第三人称" in BASE_PROMPT
    assert "不要写「视频中提到」" in BASE_PROMPT


def test_base_prompt_turns_speech_into_written_language():
    assert "书面语" in BASE_PROMPT
    assert "口头" in BASE_PROMPT


def test_base_prompt_defines_the_supplement_marker():
    """补充内容必须与课内内容可区分，且标记只允许这一个。"""
    assert SUPPLEMENT_MARKER in BASE_PROMPT
    assert "区分" in BASE_PROMPT
    assert "绝不能用这个标记" in BASE_PROMPT


def test_base_prompt_bounds_what_a_supplement_may_say():
    """补充只能做讲解性展开，不能编造事实性断言。"""
    assert "不能编造" in BASE_PROMPT
    assert "视频未说明" in BASE_PROMPT


def test_base_prompt_prefers_figure_content_over_verbal_description():
    assert "画面内容" in BASE_PROMPT
    assert "如图所示" in BASE_PROMPT
    assert "图上不清" in BASE_PROMPT


def test_every_scene_keeps_the_first_person_narrator():
    for scene, fragment in SCENE_PROMPTS.items():
        assert "第一人称" in fragment, scene


def test_every_scene_knows_the_supplement_marker():
    """三个场景都要交代补充怎么用，否则该场景下模型没有可用标记。"""
    for scene, fragment in SCENE_PROMPTS.items():
        assert SUPPLEMENT_MARKER in fragment, scene


def test_academic_scene_preserves_figures_exercises_and_derivations():
    """用户明确点名：学术类课程要更多保留图内的东西。"""
    academic = SCENE_PROMPTS["academic"]
    assert "练习题完整保留" in academic
    assert "公式推导逐步写" in academic
    assert "知识点成条" in academic
    assert "通俗讲解" in academic
    assert "图内内容优先保留" in academic
    assert "板书" in academic


def test_detailed_prompt_requires_the_supplement_marker():
    assert SUPPLEMENT_MARKER in DETAIL_PROMPTS["detailed"]


def test_merge_prompt_preserves_supplement_blocks():
    """分块合并时若把补充段落洗掉，长视频的笔记就丢了一层信息。"""
    assert "补充" in MERGE_PROMPT
    assert "原样保留" in MERGE_PROMPT


def test_assembled_academic_prompt_carries_the_whole_contract():
    prompt = generate_base_prompt("标题", "字幕正文", "标签", scene="academic", detail="detailed")
    assert "第一人称" in prompt
    assert SUPPLEMENT_MARKER in prompt
    assert SCENE_PROMPTS["academic"] in prompt
    assert DETAIL_PROMPTS["detailed"] in prompt
    assert prompt.index("**场景：学术**") < prompt.index("**篇幅：详细**")



def test_base_prompt_expects_more_than_zero_supplements():
    """真实生成暴露过的问题：模型完全没写补充段，笔记退化成纯摘要。"""
    assert "至少有两三处" in BASE_PROMPT


def test_toc_format_demands_a_bullet_list_not_a_heading_dump():
    """真实生成暴露过的第二个问题：模型把后面所有章节标题原样抄到目录下，
    目录变成一份重复的骨架，正文又重来一遍。
    """
    from app.gpt.prompt_builder import get_toc_format

    toc = get_toc_format()
    assert "`## 目录`" in toc
    assert "无序列表" in toc
    assert "逐字一致" in toc
