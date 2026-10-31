import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_module(name, relative_path):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"{name} module spec not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


url_parser = _load_module("url_parser", pathlib.Path("app") / "utils" / "url_parser.py")
video_url_validator = _load_module(
    "video_url_validator",
    pathlib.Path("app") / "validators" / "video_url_validator.py",
)


class TestVideoUrlSupport(unittest.TestCase):
    def test_extract_youtube_video_id_from_supported_url_shapes(self):
        expected_id = "dQw4w9WgXcQ"

        cases = [
            f"https://www.youtube.com/watch?v={expected_id}",
            f"https://youtu.be/{expected_id}",
            f"https://www.youtube.com/shorts/{expected_id}",
        ]

        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(
                    url_parser.extract_video_id(url, "youtube"),
                    expected_id,
                )

    def test_rejects_platforms_without_a_downloader(self):
        """入口校验必须与 SUPPORT_PLATFORM_MAP 一致（spec 005 收口）。

        youtube / douyin / kuaishou 的 downloader 已随死代码清理删除，入口若还
        放行这些链接，用户会白排一次队才在流水线里撞上 PLATFORM_NOT_SUPPORTED。
        url_parser 仍认得这些 URL 形状（它是无平台的纯工具），但校验层不再放行。
        """
        for url in (
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.douyin.com/video/7123456789012345678",
            "https://www.kuaishou.com/short-video/3xabcdef",
        ):
            with self.subTest(url=url):
                self.assertFalse(video_url_validator.is_supported_video_url(url))

    def test_still_accepts_bilibili(self):
        for url in (
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "https://b23.tv/abcdEFG",
        ):
            with self.subTest(url=url):
                self.assertTrue(video_url_validator.is_supported_video_url(url))


if __name__ == "__main__":
    unittest.main()
