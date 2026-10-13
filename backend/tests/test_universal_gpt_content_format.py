"""issue #282 回归测试：UniversalGPT 拼装 content 时按是否有图片切换 string / array 形态。

DeepSeek deepseek-chat 等非多模态模型只接受 ``content`` 为字符串，旧实现无条件
emit ``[{"type":"text","text":...}]`` 导致 ``invalid_request_error``。
"""
import importlib.util
import pathlib
import sys
import types
import unittest


def _install_stubs():
    _stub_names = [
        "app",
        "app.gpt",
        "app.models",
        "app.gpt.base",
        "app.gpt.prompt_builder",
        "app.gpt.prompt",
        "app.gpt.utils",
        "app.gpt.request_chunker",
        "app.models.gpt_model",
        "app.models.transcriber_model",
    ]
    saved = {name: sys.modules.get(name) for name in _stub_names}
    app_mod = types.ModuleType("app")
    gpt_pkg = types.ModuleType("app.gpt")
    models_pkg = types.ModuleType("app.models")

    base_mod = types.ModuleType("app.gpt.base")

    class _GPT:
        pass

    base_mod.GPT = _GPT

    prompt_builder_mod = types.ModuleType("app.gpt.prompt_builder")

    def _generate_base_prompt(**_kwargs):
        return "PROMPT_BODY"

    prompt_builder_mod.generate_base_prompt = _generate_base_prompt

    prompt_mod = types.ModuleType("app.gpt.prompt")
    prompt_mod.BASE_PROMPT = ""
    prompt_mod.AI_SUM = ""
    prompt_mod.SCREENSHOT = ""
    prompt_mod.LINK = ""
    prompt_mod.MERGE_PROMPT = "MERGE_HEAD"

    utils_mod = types.ModuleType("app.gpt.utils")

    def _fix_markdown(text):
        return text

    utils_mod.fix_markdown = _fix_markdown

    # spec 008 ticket 02：universal_gpt 现在也从 app.gpt.utils 取 load_llm_json。
    # 按本文件的既有惯用法单独载入真实现：既不必在 stub 里复制一份容错逻辑
    # （复制必然分叉），也不必为了一个纯函数去 import 整个 app 包。
    _utils_path = pathlib.Path(__file__).resolve().parents[1] / "app" / "gpt" / "utils.py"
    _utils_spec = importlib.util.spec_from_file_location("_real_gpt_utils", _utils_path)
    _real_utils = importlib.util.module_from_spec(_utils_spec)
    _utils_spec.loader.exec_module(_real_utils)
    utils_mod.load_llm_json = _real_utils.load_llm_json

    request_chunker_mod = types.ModuleType("app.gpt.request_chunker")

    class _RequestChunker:
        def __init__(self, *_args, **_kwargs):
            pass

        def group_texts_by_budget(self, texts, _builder, **_kwargs):
            return [texts]

    request_chunker_mod.RequestChunker = _RequestChunker

    gpt_model_mod = types.ModuleType("app.models.gpt_model")

    class _GPTSource:
        pass

    gpt_model_mod.GPTSource = _GPTSource

    transcriber_model_mod = types.ModuleType("app.models.transcriber_model")

    class _TranscriptSegment:
        def __init__(self, **kwargs):
            self.start = kwargs.get("start", 0)
            self.end = kwargs.get("end", 0)
            self.text = kwargs.get("text", "")

    transcriber_model_mod.TranscriptSegment = _TranscriptSegment

    sys.modules.setdefault("app", app_mod)
    sys.modules.setdefault("app.gpt", gpt_pkg)
    sys.modules.setdefault("app.models", models_pkg)
    sys.modules["app.gpt.base"] = base_mod
    sys.modules["app.gpt.prompt_builder"] = prompt_builder_mod
    sys.modules["app.gpt.prompt"] = prompt_mod
    sys.modules["app.gpt.utils"] = utils_mod
    sys.modules["app.gpt.request_chunker"] = request_chunker_mod
    sys.modules["app.models.gpt_model"] = gpt_model_mod
    sys.modules["app.models.transcriber_model"] = transcriber_model_mod
    return saved


def _restore_stubs(saved):
    for name, previous in saved.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def _load_universal_gpt_class():
    saved = _install_stubs()
    root = pathlib.Path(__file__).resolve().parents[1]
    module_path = root / "app" / "gpt" / "universal_gpt.py"
    spec = importlib.util.spec_from_file_location(
        "universal_gpt_content_format", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError("universal_gpt module spec not found")
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.UniversalGPT
    finally:
        # 载入完就不需要这些 stub 了，立刻还原，避免污染后续测试
        _restore_stubs(saved)


UniversalGPT = _load_universal_gpt_class()


class _DummyClient:
    """create_messages 不会真的调用 client，给个空壳即可。"""


def _make_gpt():
    return UniversalGPT(_DummyClient(), model="deepseek-chat")


class TestCreateMessagesContentFormat(unittest.TestCase):
    """覆盖 create_messages 在不同 video_img_urls 输入下的输出形态。"""

    def test_no_images_emits_string_content(self):
        """无图片时 content 为 str（DeepSeek / 非多模态模型可解析）。"""
        gpt = _make_gpt()

        messages = gpt.create_messages(segments=[])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIsInstance(messages[0]["content"], str)
        self.assertEqual(messages[0]["content"], "PROMPT_BODY")

    def test_empty_image_list_emits_string_content(self):
        """显式传入空列表也要走纯文本分支，避免图片字段误触发。"""
        gpt = _make_gpt()

        messages = gpt.create_messages(segments=[], video_img_urls=[])

        self.assertIsInstance(messages[0]["content"], str)

    def test_with_images_emits_multimodal_array(self):
        """有图片时保留多模态 array 形态，确保多模态模型功能不退化。"""
        gpt = _make_gpt()

        messages = gpt.create_messages(
            segments=[],
            video_img_urls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
        )

        content = messages[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 3)  # 1 text + 2 images
        self.assertEqual(content[0], {"type": "text", "text": "PROMPT_BODY"})
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(content[1]["image_url"]["url"], "https://example.com/a.jpg")
        self.assertEqual(content[1]["image_url"]["detail"], "auto")
        self.assertEqual(content[2]["image_url"]["url"], "https://example.com/b.jpg")

    def test_no_image_url_field_when_no_images(self):
        """纯文本响应里不应该出现 image_url 关键字 —— 这是触发 DeepSeek 400 的根因。"""
        gpt = _make_gpt()

        messages = gpt.create_messages(segments=[])

        import json
        serialized = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn("image_url", serialized)


class TestBuildMergeMessagesContentFormat(unittest.TestCase):
    """合并阶段从不带图片，应该统一走 string content 路径。"""

    def test_merge_messages_use_string_content(self):
        """否则长视频 chunk 后的合并阶段还会复现 issue #282 错误。"""
        gpt = _make_gpt()

        messages = gpt._build_merge_messages(["partial-A", "partial-B"])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertIsInstance(messages[0]["content"], str)
        self.assertIn("MERGE_HEAD", messages[0]["content"])
        self.assertIn("partial-A", messages[0]["content"])
        self.assertIn("partial-B", messages[0]["content"])

    def test_merge_messages_no_image_url_field(self):
        gpt = _make_gpt()

        messages = gpt._build_merge_messages(["x"])

        import json
        serialized = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn("image_url", serialized)


if __name__ == "__main__":
    unittest.main()
