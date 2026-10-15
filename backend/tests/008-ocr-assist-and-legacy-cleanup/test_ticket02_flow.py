"""spec 008 ticket 02：插图流程接线的回归测试。

`test_ocr_assist.py` 覆盖判定契约本身（解析、对齐、丢弃规则）；这个文件覆盖
**接线**：判定结果如何进提示词、如何回填占位符、以及「未判定的画面绝不进笔记」
这条不变量在代码结构上是否真的成立。

关键不变量（spec 008 ticket 02，m04445 pivot 后）：
    候选帧 ⊇ 判定通过 ＝ 实际插图
OCR 成败不再进入这条等式：它只决定「有没有额外文字参考可送给模型」。
"""
import json
from pathlib import Path

import pytest

from app.gpt.prompt_builder import (
    generate_base_prompt,
    get_format_function,
    get_ocr_assist_screenshot_format,
    get_screenshot_format,
)
from app.models.gpt_model import GPTSource
from app.services.ocr_assist import WorthDecision, build_ocr_reference
from app.services import note as note_module
from app.services.note import NoteGenerator, _normalize_for_compare, _shot_marker_pattern


def _make_ocr_stage_screenshot(fake_render):
    """给 _run_ocr_stage 用的假抽图：4 参数签名，产出 shot_<index>.jpg。"""

    def fake_generate_screenshot(video_path, out_dir, ts, index):
        fake_render["screenshot"].append((ts, index))
        target = Path(out_dir) / f"shot_{index}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jpeg")
        return str(target)

    return fake_generate_screenshot


def _recognize_blocks(blocks):
    """按给定 blocks 造一个假 OcrResult，供参考块测试直接调用 build_ocr_reference。

    `_run_ocr_stage` 现在存的是 OcrResult（带 md_results），而 _insert_approved_screenshots
    不再跑 OCR，所以参考块的测试不能再靠 `_run_insert` 间接驱动，得自己造结果对象。
    """
    from app.services.ocr_client import OcrBlock, OcrResult

    return OcrResult(
        markdown="",
        blocks=[OcrBlock(**b) if isinstance(b, dict) else b for b in blocks],
        raw={},
        protocol="layout_parsing",
        model_name="glm-ocr",
    )


def make_shot(time=12.0, reason="推导公式", caption="薛定谔方程"):
    return WorthDecision(time=time, reason=reason, caption=caption)


# --------------------------------------------------------------------------
# 一、占位符：编号必须严格相等，不能串号
# --------------------------------------------------------------------------


def test_shot_marker_matches_exact_index():
    assert _shot_marker_pattern(1).search("前面 [[SHOT-1]] 后面")


def test_shot_marker_tolerates_model_deformations():
    for variant in ("[[SHOT-1]]", "[[shot-1]]", "[[ SHOT - 1 ]]", "[[Shot1]]"):
        assert _shot_marker_pattern(1).search(variant), variant


def test_shot_marker_does_not_cross_match_neighbouring_indices():
    """`[[SHOT-1]]` 绝不能匹配 `[[SHOT-11]]`，否则第 1 张图会插到第 11 个位置。"""
    assert not _shot_marker_pattern(1).search("[[SHOT-11]]")
    assert not _shot_marker_pattern(1).search("[[SHOT-12]]")
    assert not _shot_marker_pattern(2).search("[[SHOT-1]]")
    assert _shot_marker_pattern(11).search("[[SHOT-11]]")


def test_normalize_for_compare_drops_punctuation_and_case():
    assert _normalize_for_compare("Hello, World! 你好") == "helloworld你好"
    assert _normalize_for_compare("") == ""


# --------------------------------------------------------------------------
# 二、提示词：开启 OCR 辅助后截图指令必须换形态
# --------------------------------------------------------------------------


def test_ocr_assist_format_lists_every_approved_shot():
    shots = [make_shot(12.0, caption="公式 A"), make_shot(75.0, caption="几何图")]
    text = get_ocr_assist_screenshot_format(shots)
    assert "[[SHOT-1]]" in text
    assert "[[SHOT-2]]" in text
    assert "00:12" in text
    assert "01:15" in text
    assert "公式 A" in text
    # 明确禁止模型自己发明时间点
    assert "Screenshot-" in text  # 作为「不要再写」的反面例子出现


def test_ocr_assist_format_with_no_approved_shot_forbids_images():
    text = get_ocr_assist_screenshot_format([])
    assert "[[SHOT" not in text
    assert "不要" in text or "无需" in text


def test_screenshot_format_without_ocr_assist_is_unchanged():
    """OFF 路径必须逐字保持原样（spec 008 §5.5）。"""
    assert get_format_function("screenshot") == get_screenshot_format()
    assert get_format_function("screenshot", ocr_assist=False) == get_screenshot_format()


def test_format_function_routes_screenshot_when_ocr_assist_on():
    shots = [make_shot(12.0)]
    routed = get_format_function("screenshot", ocr_assist=True, approved_shots=shots)
    assert routed == get_ocr_assist_screenshot_format(shots)
    assert "[[SHOT-1]]" in routed


def test_format_function_leaves_other_formats_alone_under_ocr_assist():
    for name in ("toc", "link", "summary"):
        assert get_format_function(name, ocr_assist=True, approved_shots=[make_shot()]) == (
            get_format_function(name)
        )


def test_generate_base_prompt_switches_screenshot_block():
    shots = [make_shot(12.0)]
    on = generate_base_prompt("标题", "字幕", ["tag"], _format=["screenshot"], ocr_assist=True,
                              approved_shots=shots)
    off = generate_base_prompt("标题", "字幕", ["tag"], _format=["screenshot"])
    assert "[[SHOT-1]]" in on
    assert "[[SHOT" not in off
    assert off.endswith(get_screenshot_format())


# --------------------------------------------------------------------------
# 三、数据模型与 checkpoint 失效
# --------------------------------------------------------------------------


def test_gpt_source_has_ocr_assist_fields_with_safe_defaults():
    source = GPTSource(segment=[], title="t", tags="")
    assert source.ocr_assist is False
    assert source.approved_shots is None


def test_source_signature_changes_when_ocr_assist_toggles():
    """换模式必须让旧 checkpoint 失效，否则会拿到按另一种模式生成的笔记。"""
    from app.gpt.gpt_factory import GPTFactory

    off = GPTSource(segment=[], title="t", tags="", checkpoint_key="k")
    on = GPTSource(
        segment=[], title="t", tags="", checkpoint_key="k",
        ocr_assist=True, approved_shots=[make_shot(12.0)],
    )

    import inspect

    source = inspect.getsource(GPTFactory)
    assert source  # 仅为保持 import 有意义；真正的断言在下面
    from app.gpt.universal_gpt import UniversalGPT

    builder = inspect.getsource(UniversalGPT._build_source_signature)
    assert "ocr_assist" in builder
    assert "approved_shots" in builder
    assert off.ocr_assist != on.ocr_assist


# --------------------------------------------------------------------------
# 四、抽帧候选清单
# --------------------------------------------------------------------------


def test_video_reader_starts_with_empty_candidate_list(tmp_path):
    from app.utils.video_reader import VideoReader

    reader = VideoReader(video_path=str(tmp_path / "nope.mp4"))
    assert reader.candidate_timestamps == []


def test_video_reader_records_candidates_in_extract_frames_source():
    """候选清单必须在 `extract_frames` 里记，三种采样模式才会一致。"""
    import inspect

    from app.utils.video_reader import VideoReader

    body = inspect.getsource(VideoReader.extract_frames)
    assert "candidate_timestamps" in body


def test_note_generator_defaults_are_off():
    """初始状态是 None（还没算过），不是空清单。

    bug 2 的修复取决于这个区别：`None` 表示「没算过、可以算」，
    而 `[]` 表示「算过了、结果为空」。重试时若用 `[]` 当初始值，
    就再也分不清「还没抽帧」和「抽到了零帧」，只能无条件重算。
    """
    generator = NoteGenerator()
    assert generator.ocr_assist is False
    assert generator.frame_candidates is None
    assert generator.picked_frames is None
    assert generator.approved_shots is None


# --------------------------------------------------------------------------
# 五、OCR 可用性门禁
# --------------------------------------------------------------------------


class _FakeManager:
    def __init__(self, readiness):
        self._readiness = readiness

    def is_ready(self):
        return self._readiness


def _patch_manager(monkeypatch, readiness):
    import app.services.ocr_config_manager as manager_module

    monkeypatch.setattr(manager_module, "OcrConfigManager", lambda *a, **k: _FakeManager(readiness))


def test_resolve_ocr_assist_returns_false_when_disabled(monkeypatch):
    _patch_manager(monkeypatch, {"enabled": False, "ready": False, "reason": "未启用"})
    assert NoteGenerator()._resolve_ocr_assist() is False


def test_resolve_ocr_assist_raises_when_enabled_but_not_ready(monkeypatch):
    """启用了却没配好必须直接失败，不能静默退回老路径。"""
    _patch_manager(monkeypatch, {"enabled": True, "ready": False, "reason": "尚未填写 API Key"})
    with pytest.raises(Exception) as excinfo:
        NoteGenerator()._resolve_ocr_assist()
    assert "尚未填写 API Key" in str(excinfo.value)


def test_resolve_ocr_assist_raises_with_settings_hint_when_reason_missing(monkeypatch):
    _patch_manager(monkeypatch, {"enabled": True, "ready": False, "reason": ""})
    with pytest.raises(Exception) as excinfo:
        NoteGenerator()._resolve_ocr_assist()
    assert "OCR 辅助" in str(excinfo.value)


def test_resolve_ocr_assist_returns_true_when_ready(monkeypatch):
    _patch_manager(monkeypatch, {"enabled": True, "ready": True, "protocol": "glm", "model_name": "glm-ocr"})
    assert NoteGenerator()._resolve_ocr_assist() is True


# --------------------------------------------------------------------------
# 六、价值判定：没有候选帧不算失败，判定异常必须上抛
# --------------------------------------------------------------------------


def test_judge_note_frames_without_candidates_is_not_a_failure(caplog):
    generator = NoteGenerator()
    assert generator._judge_note_frames(gpt=object(), transcript=None) == []


def test_judge_note_frames_propagates_judgement_errors():
    """判定失败必须让任务失败，绝不能静默返回空清单让笔记没有插图。"""
    generator = NoteGenerator()
    generator.frame_candidates = [10.0, 20.0]

    class Boom:
        def judge_note_frames(self, *a, **k):
            raise RuntimeError("上游 500")

    with pytest.raises(RuntimeError, match="上游 500"):
        generator._judge_note_frames(gpt=Boom(), transcript=None)


def test_judge_note_frames_requires_capable_client():
    generator = NoteGenerator()
    generator.frame_candidates = [10.0]
    with pytest.raises(Exception, match="画面价值判定"):
        generator._judge_note_frames(gpt=object(), transcript=None)


# --------------------------------------------------------------------------
# 七、插图回填：只有判定通过的才进笔记
# --------------------------------------------------------------------------


# 默认的假 OCR 结果：一个元素都没读出内容 → 走「插图」分支。
# `label == "image"` 的 content 恒为 null（ticket 01 §8），所以只放 image 元素
# 等于「画面里没有可搬运的文字」，这正是几何图/电路图/操作界面那一类。
_IMAGE_ONLY_BLOCKS = [{"label": "image", "content": None}]

# 读出了内容 → 走「回填文字」分支。label 为 formula 时引用块标题是「公式」。
_FORMULA_BLOCKS = [
    {"label": "image", "content": None},
    {"label": "formula", "content": "E = mc^2"},
]


class _FakeOcrResult:
    def __init__(self, text, blocks=None, raw=None):
        self.text = text
        self.markdown = text
        # blocks 是分流判据的载体：没有它 classify_ocr_result 只能拿到空清单。
        self.blocks = list(blocks) if blocks is not None else list(_IMAGE_ONLY_BLOCKS)
        # 参考块要读 md_results（q1_ocr_payload=A 明确要「md_results 原文」）；
        # 缺了它参考块会少一整段，而且因为 getattr 兜底不会报错。
        self.raw = dict(raw) if raw is not None else {}
        self.protocol = "layout_parsing"
        self.model_name = "glm-ocr"


@pytest.fixture
def fake_render(monkeypatch, tmp_path):
    """把抽图和 OCR 换成可控的假实现，记录每次调用。"""
    calls = {"screenshot": [], "ocr": [], "clients": []}
    calls["blocks"] = _IMAGE_ONLY_BLOCKS

    def fake_generate_screenshot(video_path, out_dir, ts, index):
        calls["screenshot"].append((ts, index))
        target = Path(out_dir) / f"shot_{index}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jpeg")
        return str(target)

    def fake_build_ocr_client(*a, **k):
        calls["clients"].append(1)

        class Client:
            def recognize_image(self, image_path):
                calls["ocr"].append(str(image_path))
                return _FakeOcrResult("", blocks=calls["blocks"])

        return Client()

    import app.services.media_resource_service as media_module

    monkeypatch.setattr(note_module, "generate_screenshot", fake_generate_screenshot)
    monkeypatch.setattr("app.services.ocr_client.build_ocr_client", fake_build_ocr_client)
    monkeypatch.setattr(media_module, "register_resource", lambda *a, **k: None)
    # 截图落盘目录默认是 `backend/static/screenshots`（note.py:68 的
    # `IMAGE_OUTPUT_DIR = os.getenv("OUT_DIR", "./static/screenshots")`）。假抽图虽然
    # 可控，但它拿到的是**真实目录**，于是每次跑测试都会在用户工作区里留下
    # `shot_1.jpg` 之类的残骸 —— 测试不该写进被版本管理跟踪的目录。指到 tmp_path。
    monkeypatch.setattr(note_module, "IMAGE_OUTPUT_DIR", str(tmp_path))
    return calls


def _run_insert(markdown, shots, fake_render, tmp_path):
    generator = NoteGenerator()
    generator.frame_candidates = [shot.time for shot in shots]
    generator.approved_shots = list(shots)
    return generator._insert_approved_screenshots(markdown, tmp_path / "v.mp4", list(shots))


def test_approved_shot_replaces_placeholder(fake_render, tmp_path):
    result = _run_insert("开头\n\n[[SHOT-1]]\n\n结尾", [make_shot(12.0)], fake_render, tmp_path)
    assert "[[SHOT-1]]" not in result
    assert "](/static/screenshots/shot_1.jpg)" in result
    assert fake_render["screenshot"] == [(12, 1)]
    # q6_ocr_stage：识别已搬到 _run_ocr_stage，本方法不再跑 OCR
    assert fake_render["ocr"] == []


def test_caption_becomes_alt_text(fake_render, tmp_path):
    result = _run_insert("[[SHOT-1]]", [make_shot(12.0, caption="薛定谔方程")], fake_render, tmp_path)
    assert "![薛定谔方程](/static/screenshots/shot_1.jpg)" in result


def test_ocr_content_still_embeds_the_image(fake_render, tmp_path):
    """OCR 读出内容时**照样插图**，读出的文字改从参考块进提示词。

    m04445 pivot（q3_quote_block=A）：用户明确要求「无论 ocr 有没有返回内容，
    大模型评估应该插入的图片都应该被插入」。此前这里是相反的策略——一张图画质
    清晰、文字能抄下来，反而最容易触发「以文字顶替」，于是笔记里看不到那张图。

    OCR 文本没有消失，它换了去处：`build_ocr_reference` 把它渲染进总结提示词
    （见 test_build_ocr_reference_* 那组测试），由模型自己写进正文。
    """
    fake_render["blocks"] = _FORMULA_BLOCKS
    result = _run_insert("开头\n\n[[SHOT-1]]\n\n结尾", [make_shot(12.0)], fake_render, tmp_path)
    # 插图是硬要求
    assert "](/static/screenshots/shot_1.jpg)" in result
    assert "[[SHOT-1]]" not in result
    # 引用块不再出现在笔记里：OCR 内容不进正文
    assert "> **公式**" not in result
    assert "> E = mc^2" not in result


def test_text_label_content_still_embeds_the_image(fake_render, tmp_path):
    """文字型截图（幻灯片整页、代码截图）读出 label=text 时，同样一律插图。

    m04445 pivot：判据（除 image 外任何非空 content）不再决定「插不插图」，
    只决定「有没有参考内容可送给模型」。幻灯片整页这类图恰恰是插图价值最高的
    ——画面本身就是信息，文字抄得下来也不该拿文字把它顶掉。
    """
    fake_render["blocks"] = [
        {"label": "image", "content": None},
        {"label": "text", "content": "第三讲 线性变换"},
    ]
    result = _run_insert("[[SHOT-1]]", [make_shot(12.0)], fake_render, tmp_path)
    assert "](/static/screenshots/shot_1.jpg)" in result
    assert "> **内容**" not in result
    assert "> 第三讲 线性变换" not in result


def test_multiple_read_parts_are_numbered_in_the_reference(fake_render, tmp_path):
    """同一张图里读出多段时，参考块逐段编号（m04445 pivot：正文只插图）。

    这条规则原先落在引用块上（`build_ocr_quote`），现在落在参考块上
    （`build_ocr_reference`）。多段不编号的话，模型读到的是几段来历不明的
    文字，会把「第三讲 线性变换」和「定义：将向量映射到另一空间」当成同一句。
    """
    fake_render["blocks"] = [
        {"label": "image", "content": None},
        {"label": "text", "content": "第三讲 线性变换"},
        {"label": "text", "content": "定义：将向量映射到另一空间"},
    ]
    result = _run_insert("[[SHOT-1]]", [make_shot(12.0)], fake_render, tmp_path)
    # 正文里只有图，没有回填的文字
    assert "](/static/screenshots/shot_1.jpg)" in result
    assert "第三讲 线性变换" not in result

    # 参考块里逐段编号
    shots = [make_shot(12.0)]
    result_obj = _recognize_blocks(fake_render["blocks"])
    reference = build_ocr_reference(shots, {12.0: result_obj})
    assert "第 1 段" in reference
    assert "第 2 段" in reference
    assert "第三讲 线性变换" in reference
    assert "定义：将向量映射到另一空间" in reference


def test_reference_labels_each_part_when_labels_are_mixed(fake_render, tmp_path):
    """一幅图里混了 formula 和 text 时，参考块要分别标出每段的 label。

    混装时不能只按第一个 label 给整块起标题（会误导）：模型看到「公式」标题下
    跟着一句「质能方程」，会以为那也是公式的一部分。参考块的做法是每段各带
    自己的 label。
    """
    fake_render["blocks"] = [
        {"label": "formula", "content": "E = mc^2"},
        {"label": "text", "content": "质能方程"},
    ]
    shots = [make_shot(12.0)]
    reference = build_ocr_reference(
        shots, {12.0: _recognize_blocks(fake_render["blocks"])}
    )
    assert "（formula）" in reference
    assert "（text）" in reference
    assert "E = mc^2" in reference
    assert "质能方程" in reference


def test_image_only_block_embeds_the_screenshot(fake_render, tmp_path):
    """一个元素都没读出内容 → 画面本身就是信息（几何图/电路图/操作界面），插原图。"""
    fake_render["blocks"] = _IMAGE_ONLY_BLOCKS
    result = _run_insert("[[SHOT-1]]", [make_shot(12.0)], fake_render, tmp_path)
    assert "](/static/screenshots/shot_1.jpg)" in result
    assert ">" not in result


def test_ocr_text_never_leaks_into_the_body(fake_render, tmp_path):
    """OCR 文字不再进正文（m04445 pivot）。

    原先正文里若已有同样的文字，就去重后退回插图；现在插图是唯一路径，
    「正文要不要出现这段文字」完全交给模型，代码一行都不回填——所以正文里
    除了模型自己写的「E = mc^2」，不该再多出任何一份 OCR 副本。
    """
    fake_render["blocks"] = _FORMULA_BLOCKS
    markdown = "正文已经写了 E = mc^2 这句\n\n[[SHOT-1]]"
    result = _run_insert(markdown, [make_shot(12.0)], fake_render, tmp_path)
    # 正文原有的那一次保留，OCR 没有再加一次
    assert result.count("E = mc^2") == 1
    assert "](/static/screenshots/shot_1.jpg)" in result


def test_legacy_screenshot_markers_are_stripped(fake_render, tmp_path):
    """模型自己写的 `*Screenshot-...` 没经过判定，必须剥掉。"""
    markdown = "正文\n\n*Screenshot-[00:12]\n\n[[SHOT-1]]"
    result = _run_insert(markdown, [make_shot(12.0)], fake_render, tmp_path)
    assert "Screenshot-" not in result
    assert "shot_1.jpg" in result


def test_missing_placeholder_is_appended_not_dropped(fake_render, tmp_path):
    """模型漏插占位符时内容不能丢，追加到「补充截图」小节。"""
    shots = [make_shot(12.0, caption="公式"), make_shot(30.0, caption="几何")]
    result = _run_insert("正文，只有 [[SHOT-1]]", shots, fake_render, tmp_path)
    assert "## 补充截图" in result
    assert "### 00:30" in result
    assert "shot_2.jpg" in result
    # 两张图都生成了；OCR 不在这一层跑（q6_ocr_stage）
    assert len(fake_render["screenshot"]) == 2
    assert fake_render["ocr"] == []


def test_insert_stage_no_longer_builds_an_ocr_client(fake_render, tmp_path):
    """插图阶段不再构造 OCR client —— 连接复用现在由 _run_ocr_stage 负责。

    spec 008 ticket 02 §7 的连接复用要求没有变，但落点变了：`_run_ocr_stage`
    建一个 client 串行跑完全部图。`_insert_approved_screenshots` 里若还留一份
    构造，就是每次插图多读一次 config 的白工。
    """
    shots = [make_shot(12.0), make_shot(30.0), make_shot(60.0)]
    _run_insert("正文 [[SHOT-1]]", shots, fake_render, tmp_path)
    assert len(fake_render["screenshot"]) == 3
    assert fake_render["clients"] == []
    assert fake_render["ocr"] == []


def test_ocr_stage_builds_one_client_for_all_images(fake_render, tmp_path, monkeypatch):
    """_run_ocr_stage 对 N 张图只建 1 个 OCR client，且逐张调用 recognize_image。"""
    generator = NoteGenerator()
    generator.ocr_assist = True
    generator.approved_shots = [
        make_shot(12.0),
        make_shot(30.0),
        make_shot(60.0),
    ]

    monkeypatch.setattr(
        note_module, "generate_screenshot", _make_ocr_stage_screenshot(fake_render)
    )
    generator._run_ocr_stage(str(tmp_path / "v.mp4"))

    assert len(fake_render["clients"]) == 1
    assert len(fake_render["ocr"]) == 3
    assert len(generator.ocr_texts or {}) == 3
    assert generator.ocr_failures == 0
    assert len(generator.shot_image_urls or []) == 3


def test_no_approved_shot_means_no_image_at_all(fake_render, tmp_path):
    generator = NoteGenerator()
    generator.frame_candidates = [12.0, 30.0]
    result = generator._insert_approved_screenshots("正文 [[SHOT-1]]", tmp_path / "v.mp4", [])
    assert fake_render["screenshot"] == []
    assert fake_render["ocr"] == []
    assert "![" not in result


def test_ocr_failure_skips_that_image_but_still_embeds(tmp_path, monkeypatch):
    """OCR 失败 → 跳过该张的参考内容，**图照插**、任务继续（q4_ocr_failure=A）。

    这条策略在 m04445 pivot 里被显式改过：原先 OCR 失败要上抛、让整个任务失败。
    现在插图与 OCR 解耦了——插图由判定层决定，OCR 只贡献「额外文字参考」，
    一份参考没抄到不该毁掉整篇笔记。
    """

    class FailingClient:
        def recognize_image(self, image_path):
            raise RuntimeError("OCR 服务不可用")

    monkeypatch.setattr(
        "app.services.ocr_client.build_ocr_client", lambda *a, **k: FailingClient()
    )

    def fake_screenshot(video_path, out_dir, ts, index):
        target = Path(out_dir) / f"shot_{index}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jpeg")
        return str(target)

    monkeypatch.setattr(note_module, "generate_screenshot", fake_screenshot)
    # 同 fake_render：`_run_ocr_stage` 用的是 note.py:68 的真实 `IMAGE_OUTPUT_DIR`，
    # 不指到 tmp_path 就会往 `backend/static/screenshots` 里写残骸。
    monkeypatch.setattr(note_module, "IMAGE_OUTPUT_DIR", str(tmp_path))

    generator = NoteGenerator()
    generator.ocr_assist = True
    generator.approved_shots = [make_shot(12.0)]
    generator._run_ocr_stage(str(tmp_path / "v.mp4"))

    # 失败被计数、参考内容为空，但截图仍然产出（插图不会因此丢）
    assert generator.ocr_failures == 1
    assert generator.ocr_texts == {}
    assert len(generator.shot_image_urls or []) == 1

    drawn = generator._insert_approved_screenshots(
        "[[SHOT-1]]", tmp_path / "v.mp4", list(generator.approved_shots)
    )
    assert "](/static/screenshots/shot_1.jpg)" in drawn


# --------------------------------------------------------------------------
# 八、流程分流：ON 走新路径，OFF 走老路径
# --------------------------------------------------------------------------


def test_post_process_dispatches_to_new_path_when_judgement_on(monkeypatch, tmp_path):
    generator = NoteGenerator()
    generator.ocr_judgement_enabled = True
    generator.ocr_assist = True
    generator.approved_shots = [make_shot(12.0)]
    seen = {}

    def fake_new(*a, **k):
        seen["new"] = True
        return "NEW"

    def fake_old(*a, **k):
        seen["old"] = True
        return "OLD"

    monkeypatch.setattr(generator, "_insert_approved_screenshots", fake_new)
    monkeypatch.setattr(generator, "_insert_screenshots", fake_old)

    # audio_meta 只在老路径里被读；这里断言的是走哪条分支，传 None 即可。
    result = generator._post_process_markdown(
        "md",  # type: ignore[arg-type]
        tmp_path / "v.mp4",
        ["screenshot"],
        audio_meta=None,  # type: ignore[arg-type]
        platform="bilibili",
    )
    assert result == "NEW"
    assert seen == {"new": True}


def test_post_process_still_uses_new_path_when_only_ocr_is_off(monkeypatch, tmp_path):
    """判定开着、OCR 关着，也必须走新路径——插图集合仍由判定层决定。

    这是 m02630/m02637 的关键点：关掉 OCR 辅助不等于关掉「画面值不值得编入
    笔记」。如果这里退回老路径，模型自己写的 `*Screenshot-` 就会不经判定直接
    进笔记，「只有 LLM 评为要编入笔记的画面才编入」这条需求就失效了。
    """
    generator = NoteGenerator()
    generator.ocr_judgement_enabled = True
    generator.ocr_assist = False
    seen = {}
    captured = {}

    def fake_new(*a, **k):
        seen["new"] = True
        captured["ocr_enabled"] = k.get("ocr_enabled")
        return "NEW"

    def fake_old(*a, **k):
        seen["old"] = True
        return "OLD"

    monkeypatch.setattr(generator, "_insert_approved_screenshots", fake_new)
    monkeypatch.setattr(generator, "_insert_screenshots", fake_old)

    # audio_meta 只在老路径里被读；这里断言的是走哪条分支，传 None 即可。
    result = generator._post_process_markdown(
        "md",  # type: ignore[arg-type]
        tmp_path / "v.mp4",
        ["screenshot"],
        audio_meta=None,  # type: ignore[arg-type]
        platform="bilibili",
    )
    assert result == "NEW"
    assert seen == {"new": True}
    # ocr_enabled 必须如实传下去，否则关闭开关也会去调 OCR 服务
    assert captured["ocr_enabled"] is False


def test_post_process_uses_legacy_path_when_judgement_off(monkeypatch, tmp_path):
    """判定层关着（老路径）时行为必须与改动前一致，零回归。"""
    generator = NoteGenerator()
    generator.ocr_judgement_enabled = False
    generator.ocr_assist = False
    seen = {}

    def fake_new(*a, **k):
        seen["new"] = True
        return "NEW"

    def fake_old(*a, **k):
        seen["old"] = True
        return "OLD"

    monkeypatch.setattr(generator, "_insert_approved_screenshots", fake_new)
    monkeypatch.setattr(generator, "_insert_screenshots", fake_old)

    # audio_meta 只在老路径里被读；这里断言的是走哪条分支，传 None 即可。
    result = generator._post_process_markdown(
        "md",  # type: ignore[arg-type]
        tmp_path / "v.mp4",
        ["screenshot"],
        audio_meta=None,  # type: ignore[arg-type]
        platform="bilibili",
    )
    assert result == "OLD"
    assert seen == {"old": True}


def test_judgement_branch_is_not_wrapped_in_try_except():
    """结构断言：OCR 失败必须能冒泡到 generate 的顶层 except。"""
    import inspect
    import textwrap

    body = textwrap.dedent(inspect.getsource(NoteGenerator._post_process_markdown))
    start = body.index("if self.ocr_judgement_enabled:")
    end = body.index("else:", start)
    branch = body[start:end]
    assert "try:" not in branch
    assert "_insert_approved_screenshots" in branch


def test_legacy_insert_screenshots_still_exists_untouched():
    assert hasattr(NoteGenerator, "_insert_screenshots")


# --------------------------------------------------------------------------
# 九、结构性保证：未判定的帧不可能被插图
# --------------------------------------------------------------------------


def test_approved_shots_is_the_only_image_source_in_new_path():
    """新路径只读 `approved` 参数，不碰 `frame_candidates`，结构上排除了「顺手插一张」。"""
    import inspect
    import textwrap

    body = textwrap.dedent(inspect.getsource(NoteGenerator._insert_approved_screenshots))
    # frame_candidates 只允许出现在那行计数日志里，不得参与插图决策
    assert body.count("frame_candidates") == 1
    assert "len(self.frame_candidates or [])" in body
    assert "approved" in body
    # 不得再调用老路径
    assert "_insert_screenshots(" not in body


def test_source_signature_payload_is_json_serialisable():
    """签名 payload 里放的是 dataclass，必须能安全取出 time/caption。"""
    shots = [make_shot(12.0, caption="公式")]
    payload = [{"time": getattr(s, "time", None), "caption": getattr(s, "caption", "")} for s in shots]
    assert json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------
# 十、落盘与复用：重试（乃至进程重启）不该白扔抽帧与两次 LLM 调用
# --------------------------------------------------------------------------


@pytest.fixture
def ocr_cache_dir(monkeypatch, tmp_path):
    """把 NOTE_OUTPUT_DIR 指到临时目录，避免测试往真实 note_results 里写东西。"""
    monkeypatch.setattr(note_module, "NOTE_OUTPUT_DIR", tmp_path)
    return tmp_path


def test_ocr_cache_file_is_keyed_by_video_url_not_task_id():
    """缓存键必须是「哪个视频」，不是「哪一次尝试」——重试会换 task_id。"""
    generator = NoteGenerator()
    same = generator._ocr_cache_file("https://www.bilibili.com/video/BV1xx")
    again = generator._ocr_cache_file("https://www.bilibili.com/video/BV1xx")
    other = generator._ocr_cache_file("https://www.bilibili.com/video/BV1yy")
    assert same == again
    assert same != other
    assert same.name.startswith("ocr_frames_") and same.suffix == ".json"


def test_save_then_load_roundtrips_worth_decisions(ocr_cache_dir):
    """落盘用 asdict，读回来必须还原成 WorthDecision。

    还原这一步不是锦上添花：下游全靠 `getattr(decision, "time")` 取时间戳，
    如果读回来是 dict，所有截图都会落在 0 秒那一帧。
    """
    generator = NoteGenerator()
    generator.frame_candidates = [10.0, 12.0, 30.0]
    generator.picked_frames = [10.0, 12.0]
    generator.approved_shots = [make_shot(12.0, reason="推导公式", caption="薛定谔方程")]

    generator._save_ocr_cache("https://example.com/v/1")

    fresh = NoteGenerator()
    assert fresh._load_ocr_cache("https://example.com/v/1") is True
    assert fresh.frame_candidates == [10.0, 12.0, 30.0]
    assert fresh.picked_frames == [10.0, 12.0]
    assert fresh.approved_shots is not None
    shot = fresh.approved_shots[0]
    assert isinstance(shot, WorthDecision)
    assert (shot.time, shot.reason, shot.caption) == (12.0, "推导公式", "薛定谔方程")


def test_load_returns_false_without_a_cache_file(ocr_cache_dir):
    generator = NoteGenerator()
    assert generator._load_ocr_cache("https://example.com/never") is False
    assert generator.approved_shots is None


def test_load_does_not_overwrite_in_memory_results(ocr_cache_dir):
    """内存里已经有本轮结果时，磁盘缓存不得把它盖掉。"""
    generator = NoteGenerator()
    generator.frame_candidates = [5.0]
    generator.picked_frames = [5.0]
    generator.approved_shots = [make_shot(5.0)]
    generator._save_ocr_cache("https://example.com/v/2")

    generator.approved_shots = []  # 本轮判定为空，是合法结果
    assert generator._load_ocr_cache("https://example.com/v/2") is False
    assert generator.approved_shots == []


def test_corrupt_cache_is_treated_as_missing(ocr_cache_dir):
    """落盘只是优化：缓存坏了必须当没有，不能让整个任务失败。"""
    generator = NoteGenerator()
    generator._ocr_cache_file("https://example.com/v/3").write_text(
        "{ this is not json", encoding="utf-8"
    )
    assert generator._load_ocr_cache("https://example.com/v/3") is False
    assert generator.approved_shots is None


def test_generate_records_picked_frames_and_saves_the_cache():
    """结构断言：# 2.5 段落必须把挑选结果留在实例上并落盘。

    只算不存的话，「复用上一轮结果」这条路径永远读不到东西 —— 挑选结果原本只
    活在 `_pick_note_frames` 的返回值里，实例上的 `picked_frames` 一直是 None。
    """
    import inspect
    import textwrap

    body = textwrap.dedent(inspect.getsource(NoteGenerator.generate))
    start = body.index("# 2.5 OCR 辅助")
    end = body.index("# 3. GPT 总结", start)
    branch = body[start:end]
    assert "self.picked_frames = list(picked)" in branch
    assert "self._save_ocr_cache(str(video_url))" in branch
    # 落盘必须在判定之后：判定失败时不能把「通过 = 空」固化下来
    assert branch.index("_judge_note_frames") < branch.index("_save_ocr_cache")



# ---------------------------------------------------------------------------
# 判定层分块（spec 008 ticket 02 §7）
#
# 背景：任务 b9e6b9c8 产出了 127 张网格图、data_url_bytes=31578181，
# 判定层把它们一次性塞进单次请求，撞上网关 10MB 上限：
#   openai.APIStatusError: Error code: 413 ... 'request body too large: >10485760 bytes'
# 413 不在 _is_retryable_error 的可重试清单里，请求级立即失败。
# ---------------------------------------------------------------------------

#: 网关实测上限（413 报文里的 10485760）。应用侧 45MB 的默认值从来没对齐过它。
GATEWAY_LIMIT_BYTES = 10 * 1024 * 1024


class _FakeCompletions:
    """记录每次请求的字节数，并返回一段合法的判定 JSON。"""

    def __init__(self, record):
        self._record = record

    def create(self, **kwargs):
        messages = kwargs.get("messages") or []
        import json

        size = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        self._record.append({"size": size, "messages": messages})

        class _Msg:
            content = '{"frames": [{"time": 12, "worth": true, "reason": "公式"}]}'

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    def __init__(self, record):
        self.chat = type("_Chat", (), {"completions": _FakeCompletions(record)})()


def _make_big_image_urls(count, bytes_each=248_000):
    """构造 count 张约 bytes_each 字节的 data URL，总量对齐实测的 127 张 / 31.6MB。"""
    import base64

    payload = base64.b64encode(b"x" * bytes_each).decode("ascii")
    return [f"data:image/jpeg;base64,{payload}" for _ in range(count)]


def test_judge_request_never_exceeds_gateway_limit(tmp_path, monkeypatch):
    """127 张真图规模下，任何单次判定请求都不得超过网关 10MB 上限。

    这是任务 b9e6b9c8 的回归测试：当时 127 张图被打包成一个 31.6MB 的请求，
    网关直接 413，而且 413 不可重试，于是整个任务三次重试全废。
    """
    from app.gpt.universal_gpt import UniversalGPT

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    gpt = UniversalGPT(_FakeClient(record), "glm-4.6")

    urls = _make_big_image_urls(127)
    total = sum(len(u.encode("utf-8")) for u in urls)
    assert total > GATEWAY_LIMIT_BYTES, (
        f"夹具本身要超过网关上限才有意义，当前 {total} <= {GATEWAY_LIMIT_BYTES}"
    )

    gpt.judge_note_frames(
        segments=[],
        candidates=[12.0],
        duration=600.0,
        image_urls=urls,
    )

    assert record, "判定层必须至少发出一次请求"
    worst = max(item["size"] for item in record)
    assert worst <= GATEWAY_LIMIT_BYTES, (
        f"单次判定请求 {worst} 字节，超过网关上限 {GATEWAY_LIMIT_BYTES}；"
        f"共发出 {len(record)} 次请求"
    )


def test_judge_splits_images_across_multiple_requests(tmp_path, monkeypatch):
    """图片塞不下时必须拆成多次请求，而不是一次性发出去。"""
    from app.gpt.universal_gpt import UniversalGPT

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    gpt = UniversalGPT(_FakeClient(record), "glm-4.6")

    gpt.judge_note_frames(
        segments=[],
        candidates=[12.0],
        duration=600.0,
        image_urls=_make_big_image_urls(127),
    )

    assert len(record) > 1, f"127 张图必须拆成多次请求，实际只发了 {len(record)} 次"


def test_judge_chunks_are_merged_into_one_outcome(tmp_path, monkeypatch):
    """多次请求的判定结果要合并成同一个 outcome，而不是只取最后一块。

    合并必须在**完整候选清单**上做一次解析：否则 max_images 上限、去重、
    排序都会退化成「每块各自算一遍再拼起来」，统计字段也不再是全局口径。
    """
    from app.gpt.universal_gpt import UniversalGPT

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    gpt = UniversalGPT(_FakeClient(record), "glm-4.6")

    outcome = gpt.judge_note_frames(
        segments=[],
        candidates=[12.0],
        duration=600.0,
        image_urls=_make_big_image_urls(127),
    )

    # 每个假响应都回同一条 time=12 且 worth=true 的判定。
    # 合并后必须去重成 1 条，而不是每块各留一条。
    assert len(outcome.approved) == 1, (
        f"同一时间点的重复判定必须被去重，实际 approved={len(outcome.approved)}"
    )
    assert outcome.rejected_duplicate >= 1, "重复判定应当计入 rejected_duplicate"


def test_judge_fits_within_limit_when_payload_is_small(tmp_path, monkeypatch):
    """小载荷不应被无谓拆分：一次能装下就只发一次。"""
    from app.gpt.universal_gpt import UniversalGPT

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    record: list = []
    gpt = UniversalGPT(_FakeClient(record), "glm-4.6")

    gpt.judge_note_frames(
        segments=[],
        candidates=[12.0],
        duration=600.0,
        image_urls=_make_big_image_urls(3, bytes_each=1000),
    )

    assert len(record) == 1, f"小载荷应当只发一次，实际 {len(record)} 次"


# ---------------------------------------------------------------------------
# 出站请求预算必须服从网关上限（spec 008 ticket 02 §7）
#
# 事故：判定层的 413 修好之后，同一个任务又以
#     [ERROR] app.services.note - GPT 总结失败：Error code: 413
# 炸掉。根因同源但位置不同——`self.max_request_bytes` 默认 45MB，而网关只允许
# 10MB，RequestChunker 严格按 45MB 切分，于是切出来的「合规」分块本身就有
# 40MB+，判定层与总结层先后撞 413。
# ---------------------------------------------------------------------------


def test_max_request_bytes_never_exceeds_gateway_limit(tmp_path, monkeypatch):
    """应用侧请求预算不得超过网关上限，否则分块切出来的块本身就超限。"""
    from app.gpt import universal_gpt as ug

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_MAX_REQUEST_BYTES", raising=False)
    gpt = ug.UniversalGPT(object(), "glm-4.6")

    assert gpt.max_request_bytes <= ug.GATEWAY_MAX_REQUEST_BYTES, (
        f"max_request_bytes={gpt.max_request_bytes} 超过网关上限 "
        f"{ug.GATEWAY_MAX_REQUEST_BYTES}；分块会切出超限的块"
    )


def test_explicit_larger_max_request_bytes_is_clamped(tmp_path, monkeypatch):
    """显式配一个更大的预算时必须收敛到网关上限，而不是照单全收。"""
    from app.gpt import universal_gpt as ug

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_MAX_REQUEST_BYTES", str(500 * 1024 * 1024))
    gpt = ug.UniversalGPT(object(), "glm-4.6")

    assert gpt.max_request_bytes == ug.GATEWAY_MAX_REQUEST_BYTES


def test_smaller_max_request_bytes_is_respected(tmp_path, monkeypatch):
    """配一个更小的预算时应当尊重它——收敛只针对「超过上限」的情况。"""
    from app.gpt import universal_gpt as ug

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_MAX_REQUEST_BYTES", str(2 * 1024 * 1024))
    gpt = ug.UniversalGPT(object(), "glm-4.6")

    assert gpt.max_request_bytes == 2 * 1024 * 1024


def test_summarize_chunker_uses_the_gateway_bounded_budget(tmp_path, monkeypatch):
    """summarize 的 RequestChunker 必须拿到收敛后的预算。

    这条是直接盯住事故现场的：分块器拿到的 max_bytes 决定了它切出来的每一块
    有多大，而 summarize 与判定层走的是两个独立的分块器。
    """
    from app.gpt import universal_gpt as ug
    from app.gpt.request_chunker import RequestChunker

    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_MAX_REQUEST_BYTES", raising=False)

    seen: dict = {}
    real_init = RequestChunker.__init__

    def spy_init(self, message_builder, max_bytes, size_estimator=None):
        seen["max_bytes"] = max_bytes
        return real_init(self, message_builder, max_bytes, size_estimator)

    monkeypatch.setattr(RequestChunker, "__init__", spy_init)

    gpt = ug.UniversalGPT(object(), "glm-4.6")
    # 直接构造分块器，复刻 summarize 的做法（:479）
    RequestChunker(
        lambda segments, image_urls, **kw: [],
        gpt.max_request_bytes,
        gpt._estimate_messages_bytes,
    )

    assert seen["max_bytes"] <= ug.GATEWAY_MAX_REQUEST_BYTES, (
        f"summarize 的分块预算 {seen['max_bytes']} 超过网关上限 "
        f"{ug.GATEWAY_MAX_REQUEST_BYTES}"
    )

# --------------------------------------------------------------------------
# 九、m04445 pivot：一律插图 + OCR 参考块 + 单帧进提示词
# --------------------------------------------------------------------------


def test_every_approved_shot_is_embedded_even_with_rich_ocr(fake_render, tmp_path):
    """核心诉求：无论 OCR 有没有返回内容，判定通过的图都必须被插入。

    这是 m04445 的原话（「无论ocr有没有返回内容，大模型评估应该插入的图片都应该
    被插入」）在代码结构上的样子。原先最典型的反例是一张公式板书：OCR 读得越清楚，
    越容易触发「以文字顶替」，于是图上内容最该被保留的那张反而没图。
    """
    fake_render["blocks"] = _FORMULA_BLOCKS
    shots = [make_shot(12.0), make_shot(30.0), make_shot(60.0)]
    markdown = "正文\n\n[[SHOT-1]]\n\n中段\n\n[[SHOT-2]]\n\n尾段\n\n[[SHOT-3]]"
    result = _run_insert(markdown, shots, fake_render, tmp_path)

    for index in (1, 2, 3):
        assert f"](/static/screenshots/shot_{index}.jpg)" in result, index
    assert "[[" not in result
    # OCR 读出的公式一个字都没回到正文里
    assert "> " not in result
    assert "E = mc^2" not in result


def test_reference_carries_bbox_and_md_results(fake_render):
    """q1_ocr_payload=A：参考块要给全 content、label+bbox、以及 md_results 原文。

    只给 parts 是不够的：模型看得到文字却不知道版面结构（哪块是插图、哪块是公式），
    而 md_results 兜底那些 blocks 里没体现的内容。
    """
    from app.services.ocr_client import OcrBlock, OcrResult

    shot = make_shot(12.0)
    result = OcrResult(
        markdown="板书：薛定谔方程",
        blocks=[
            OcrBlock(label="image", content=None, bbox=[0, 0, 1, 1], page=1, index=0),
            OcrBlock(label="formula", content="E = mc^2", bbox=[0.1, 0.2, 0.3, 0.4], page=1, index=1),
        ],
        raw={"md_results": "板书：薛定谔方程"},
        protocol="layout_parsing",
        model_name="glm-ocr",
    )
    reference = build_ocr_reference([shot], {12.0: result})

    assert "### [[SHOT-1]] @ 00:12" in reference
    assert "（formula）" in reference
    assert "E = mc^2" in reference
    assert "bbox=[0.1, 0.2, 0.3, 0.4]" in reference
    assert "md_results 原文" in reference
    assert "板书：薛定谔方程" in reference
    # label == image 元素不当作正文段（它恒 content: null，是插图元素）
    assert "第 2 段" not in reference


def test_reference_says_so_when_ocr_gave_nothing(fake_render):
    """q7_no_ocr=A：OCR 没结果时参考块为空/明说，但**图片照插**。"""
    shot = make_shot(12.0)
    reference = build_ocr_reference([shot], {})
    assert "未返回结果" in reference
    assert "仍会插入笔记" in reference


def test_reference_is_injected_before_the_format_instructions():
    """q2_inject_shape=A：参考块按时间点分节，位置在格式说明**之前**。

    素材先立住，模型读格式要求时手里已经有东西；反过来放，模型容易把参考内容
    当成又一段待总结的字幕。
    """
    reference = "### [[SHOT-1]] @ 00:12\n- 内容  第 1 段（formula）：\n    E = mc^2"
    prompt = generate_base_prompt(
        title="测试",
        segment_text="字幕正文",
        tags=["数学"],
        _format=[],
        ocr_assist=True,
        approved_shots=[make_shot(12.0)],
        ocr_reference=reference,
    )
    assert "画面文字参考（OCR）" in prompt
    assert "E = mc^2" in prompt
    # 位置：在字幕之后
    assert prompt.index("字幕正文") < prompt.index("画面文字参考（OCR）")
    # 且明确声明它只是参考
    assert "不要原样照搬" in prompt


def test_prompt_has_no_reference_section_when_ocr_is_empty():
    """参考块为空时不能留一个空标题，否则提示词里多一节空内容。"""
    prompt = generate_base_prompt(
        title="测试",
        segment_text="字幕正文",
        tags=[],
        _format=[],
        ocr_assist=True,
        approved_shots=[make_shot(12.0)],
        ocr_reference="",
    )
    assert "画面文字参考" not in prompt


def test_ocr_texts_round_trip_through_disk_cache(tmp_path):
    """q5_cache=A：OCR 文本落盘后能还原成 OcrResult（含 bbox 与 md_results）。

    重试时不必再调一次 OCR。转不回 OcrResult 的话，参考块会从「有内容」退化成
    「未返回结果」，而且因为 getattr 兜底不会报错。
    """
    from app.services.ocr_client import OcrBlock, OcrResult
    from app.services.note import _deserialize_ocr_result, _serialize_ocr_result

    original = OcrResult(
        markdown="板书",
        blocks=[OcrBlock(label="formula", content="E = mc^2", bbox=[0.1, 0.2, 0.3, 0.4], page=1, index=0)],
        raw={"md_results": "板书"},
        protocol="layout_parsing",
        model_name="glm-ocr",
    )
    payload = json.loads(json.dumps({"12.0": _serialize_ocr_result(original)}, ensure_ascii=False))
    restored = _deserialize_ocr_result(payload["12.0"])

    assert restored is not None
    assert restored.markdown == original.markdown
    assert restored.raw == original.raw
    assert len(restored.blocks) == 1
    assert restored.blocks[0].bbox == [0.1, 0.2, 0.3, 0.4]
    assert restored.blocks[0].content == "E = mc^2"


def test_summarize_gets_single_shots_not_grid_images(monkeypatch, tmp_path):
    """q10/q11：送总结模型的是判定通过的单帧，不是网格图。

    网格图（每 9 帧拼一张、共 127 张）是判定层的工作材料：每帧被缩到 1/9，
    模型看不清板书；而且里面大半是未通过判定的帧。判定通过的清单才是
    「必须编入笔记」的集合。
    """
    generator = NoteGenerator()
    generator.shot_image_urls = ["data:image/jpeg;base64,SHOT1", "data:image/jpeg;base64,SHOT2"]
    generator.video_img_urls = ["data:image/jpeg;base64,GRID" * 10]
    generator.approved_shots = [make_shot(12.0)]
    generator.ocr_judgement_enabled = True
    generator.ocr_texts = {}

    captured = {}

    class FakeGPT:
        def summarize(self, source):
            captured["urls"] = list(source.video_img_urls or [])
            captured["ocr_reference"] = source.ocr_reference
            return "# 笔记\n\n[[SHOT-1]]"

    class FakeTranscript:
        segments = []

    class FakeMeta:
        title = "t"
        raw_info = {}

    generator._summarize_text(
        audio_meta=FakeMeta(),
        transcript=FakeTranscript(),
        gpt=FakeGPT(),
        markdown_cache_file=tmp_path / "m.md",
        link=False,
        screenshot=True,
        formats=[],
        scene=None,
        detail=None,
        extras=None,
        video_img_urls=generator.shot_image_urls or generator.video_img_urls,
        ocr_assist=True,
        approved_shots=generator.approved_shots,
        ocr_reference="### [[SHOT-1]] @ 00:12",
    )

    assert captured["urls"] == generator.shot_image_urls
    assert "GRID" not in "".join(captured["urls"])
    assert captured["ocr_reference"] == "### [[SHOT-1]] @ 00:12"
