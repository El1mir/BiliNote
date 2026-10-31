import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "services" / "model_fallback.py"
spec = importlib.util.spec_from_file_location("model_fallback", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError("model_fallback module spec not found")
model_fallback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model_fallback)

normalize_models = model_fallback.normalize_models
as_model_dicts = model_fallback.as_model_dicts


class FakeModel:
    """模拟 openai SDK 的 Model（pydantic）对象。"""

    def __init__(self, mid, created=None, owned_by="x"):
        self.id = mid
        self.created = created
        self.object = "model"
        self.owned_by = owned_by

    def dict(self):
        return {"id": self.id, "created": self.created, "object": self.object, "owned_by": self.owned_by}


class FakeSyncPage:
    def __init__(self, data):
        self.data = data




class TestNormalizeModels(unittest.TestCase):
    def test_syncpage_with_models(self):
        page = FakeSyncPage([FakeModel("deepseek-chat"), FakeModel("deepseek-reasoner")])
        out = normalize_models(page)
        self.assertEqual([m["id"] for m in out], ["deepseek-chat", "deepseek-reasoner"])

    def test_plain_list_of_models(self):
        out = normalize_models([FakeModel("a"), FakeModel("b")])
        self.assertEqual([m["id"] for m in out], ["a", "b"])

    def test_empty_list_does_not_raise(self):
        # 关键回归：旧代码对 [] 取 .data 会 AttributeError
        self.assertEqual(normalize_models([]), [])

    def test_list_of_dicts(self):
        out = normalize_models([{"id": "x", "object": "model"}])
        self.assertEqual(out[0]["id"], "x")

    def test_drops_entries_without_id(self):
        out = normalize_models([{"object": "model"}, {"id": "ok"}])
        self.assertEqual([m["id"] for m in out], ["ok"])

    def test_none_returns_empty(self):
        self.assertEqual(normalize_models(None), [])


class TestAsModelDicts(unittest.TestCase):
    def test_shape_matches_sdk(self):
        out = as_model_dicts(["deepseek-chat"], owned_by="DeepSeek")
        self.assertEqual(out[0]["id"], "deepseek-chat")
        self.assertEqual(out[0]["object"], "model")
        self.assertEqual(out[0]["owned_by"], "DeepSeek")


if __name__ == "__main__":
    unittest.main()
