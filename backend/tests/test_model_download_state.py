"""Unit tests for app.transcriber.model_download_state（模型下载状态 + 失败原因跟踪）。

与 test_whisper_models 一样按文件路径隔离加载，并桩掉 app.utils.logger，
避免触发 app/__init__.py（会 import faster_whisper 等重依赖）。
"""
import importlib.util
import logging
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "transcriber" / "model_download_state.py"


def _load_module():
    """按文件路径加载被测模块，并把自己注入的桩模块**原样收回**。

    桩只在 exec_module 期间需要（模块顶层只用到 app.utils.logger.get_logger）。
    如果把它们留在 sys.modules，同一进程里后跑的测试就会看到 `app` 是个没有
    `__path__` 的裸模块，`from app.transcriber import ...` 直接 ModuleNotFoundError ——
    这类跨文件污染只在全量连跑时出现，单跑永远看不到。
    """
    stubbed = []
    if "app" not in sys.modules:
        app_pkg = types.ModuleType("app")
        app_pkg.__path__ = []
        sys.modules["app"] = app_pkg
        stubbed.append("app")
    if "app.utils" not in sys.modules:
        utils_pkg = types.ModuleType("app.utils")
        utils_pkg.__path__ = []
        sys.modules["app.utils"] = utils_pkg
        stubbed.append("app.utils")
    if "app.utils.logger" not in sys.modules:
        logger_mod = types.ModuleType("app.utils.logger")
        logger_mod.get_logger = lambda name=None: logging.getLogger(name or "test")
        sys.modules["app.utils.logger"] = logger_mod
        stubbed.append("app.utils.logger")
    try:
        spec = importlib.util.spec_from_file_location("model_download_state_under_test", MODULE_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for name in reversed(stubbed):
            sys.modules.pop(name, None)
    return mod


ds = _load_module()


class TestDownloadState(unittest.TestCase):
    def setUp(self):
        # 模块级单例，测试间互相隔离
        ds._status.clear()
        ds._errors.clear()

    def test_unknown_key_defaults(self):
        row = ds.status_row("tiny", downloaded=False)
        self.assertEqual(
            row,
            {"model_size": "tiny", "downloaded": False, "downloading": False, "failed": False},
        )
        self.assertNotIn("error", row)
        self.assertFalse(ds.is_downloading("tiny"))

    def test_downloading(self):
        ds.mark_downloading("tiny")
        self.assertTrue(ds.is_downloading("tiny"))
        row = ds.status_row("tiny", downloaded=False)
        self.assertTrue(row["downloading"])
        self.assertFalse(row["failed"])

    def test_failed_surfaces_error(self):
        ds.mark_failed("tiny", "401 Repository Not Found")
        row = ds.status_row("tiny", downloaded=False)
        self.assertTrue(row["failed"])
        self.assertFalse(row["downloading"])
        self.assertEqual(row["error"], "401 Repository Not Found")
        self.assertEqual(ds.get_error("tiny"), "401 Repository Not Found")

    def test_failed_without_message_has_no_error_field(self):
        ds.mark_failed("tiny")
        row = ds.status_row("tiny", downloaded=False)
        self.assertTrue(row["failed"])
        self.assertNotIn("error", row)

    def test_downloaded_overrides_failed(self):
        # 先失败后又下好：downloaded=True 时不应再回传 failed/error
        ds.mark_failed("tiny", "boom")
        row = ds.status_row("tiny", downloaded=True)
        self.assertFalse(row["failed"])
        self.assertTrue(row["downloaded"])
        self.assertNotIn("error", row)

    def test_mark_done_clears_error(self):
        ds.mark_failed("tiny", "boom")
        ds.mark_done("tiny")
        self.assertIsNone(ds.get_error("tiny"))
        row = ds.status_row("tiny", downloaded=True)
        self.assertFalse(row["failed"])

    def test_redownload_clears_previous_error(self):
        ds.mark_failed("tiny", "boom")
        ds.mark_downloading("tiny")  # 重新开始下载
        self.assertIsNone(ds.get_error("tiny"))
        row = ds.status_row("tiny", downloaded=False)
        self.assertTrue(row["downloading"])
        self.assertFalse(row["failed"])
        self.assertNotIn("error", row)

    def test_secondary_key_is_independent(self):
        # 同一个 size 挂在另一条 key 上时互不影响（历史 mlx-{size} 前缀即此机制）
        ds.mark_failed("alt-tiny", "alt boom")
        ds.mark_downloading("tiny")
        whisper_row = ds.status_row("tiny", downloaded=False)
        alt_row = ds.status_row("tiny", downloaded=False, key="alt-tiny")
        self.assertTrue(whisper_row["downloading"])
        self.assertFalse(whisper_row["failed"])
        self.assertTrue(alt_row["failed"])
        self.assertEqual(alt_row["error"], "alt boom")


if __name__ == "__main__":
    unittest.main()
