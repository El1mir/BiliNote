"""spec 006 ticket 05：下载器的「只取元信息」路径。

背景：任务已经有字幕时不需要下载音视频，只需要标题/时长/封面。B 站的
`download(skip_download=True)` 过去会带着 `format='bestaudio[ext=m4a]/bestaudio/best'`
真下载一遍；而且该参数当时根本不存在（TypeError 被 note.py 的宽 except 吞掉）。

这里固定三件事：
  1. skip_download ⇒ skip_download + ignore_no_formats_error，且 extract_info(download=False)；
  2. ext=None 时回退 .m4a（不能拼出 "xxx.None"）；
  3. 正常下载仍然选择音频格式，且不打开 ignore_no_formats_error；
另外用 AST 校验 Bilibili 下载器的 download() 对齐了 skip_download 接口。

2026-10-05 收口（spec 005 死代码清理）：YouTube / 抖音 / 快手 / 小宇宙的下载器已删除，
`SUPPORT_PLATFORM_MAP` 只剩 bilibili（见 `app/services/constant.py`）。这条 AST 契约
随之只对 bilibili 生效 —— 它校验的是「当前真正会被实例化的那个下载器」。
"""
import ast
import importlib.util
import logging
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "app" / "downloaders" / "bilibili_downloader.py"
PLATFORM_MODULES = {
    "bilibili": MODULE_PATH,
}


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    # Replace a previous test's stub instead of inheriting it (see
    # test_youtube_metadata_only.py for why this matters).
    sys.modules[name] = module
    return module


# 这些 stub 会把 app / app.services 等换成没有 __path__ 的裸模块。载入目标模块
# 时必须留着它们，但载入之后必须还原——否则同一进程里其后任何真正
# `import app.services.xxx` 的测试都会报 "'app.services' is not a package"。
_STUB_NAMES = [
    "app",
    "app.downloaders",
    "app.models",
    "app.services",
    "app.utils",
    "app.utils.logger",
    "app.downloaders.base",
    "app.downloaders.bilibili_dm_patch",
    "app.downloaders.bilibili_subtitle",
    "app.models.notes_model",
    "app.models.transcriber_model",
    "app.services.cookie_manager",
    "app.utils.path_helper",
    "app.utils.url_parser",
]


def _restore_stubs(saved):
    for name, previous in saved.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


class _Downloader:
    def __init__(self):
        self.cache_data = "/tmp"


class _AudioDownloadResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _DownloadQuality:
    """``app.enmus.note_enums.DownloadQuality`` 的替身。

    真实枚举是 str 混入（``class DownloadQuality(str, enum.Enum)``），而下载器签名用
    ``DownloadQuality.fast`` 当默认值——只给一个裸 ``str`` 已经不足以让模块加载成功
    （会抛 ``type object 'str' has no attribute 'fast'``）。
    """

    fast = "fast"
    medium = "medium"
    slow = "slow"

def _load_bilibili_downloader():
    saved = {name: sys.modules.get(name) for name in _STUB_NAMES}
    _stub("app")
    _stub("app.downloaders")
    _stub("app.models")
    _stub("app.services")
    _stub("app.utils")
    _stub("app.utils.logger", get_logger=lambda name: logging.getLogger(name))
    _stub(
        "app.downloaders.base",
        Downloader=_Downloader,
        DownloadQuality=_DownloadQuality,
        QUALITY_MAP={"fast": "32", "medium": "64", "slow": "128"},
        YDL_RETRY_OPTS={"retries": 3, "fragment_retries": 3, "socket_timeout": 30},
    )
    _stub("app.downloaders.bilibili_dm_patch", apply_bilibili_dm_img_patch=lambda: None)
    _stub("app.downloaders.bilibili_subtitle", BilibiliSubtitleFetcher=object)
    _stub("app.models.notes_model", AudioDownloadResult=_AudioDownloadResult)
    _stub("app.models.transcriber_model", TranscriptResult=object, TranscriptSegment=object)
    _stub(
        "app.services.cookie_manager",
        CookieConfigManager=type(
            "CookieConfigManager", (), {"get": lambda self, platform=None: None}
        ),
    )
    _stub("app.utils.path_helper", get_data_dir=lambda: "/tmp")
    _stub("app.utils.url_parser", extract_video_id=lambda url, platform: "BV1test")

    spec = importlib.util.spec_from_file_location("bilibili_downloader", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("bilibili_downloader module spec not found")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        # 必须无条件还原：加载失败时若留着这些桩，同一进程里其后任何真正的
        # ``import app.services.xxx`` 都会报 "'app.services' is not a package"，
        # 一个 import 错误会连累几十个无关用例。
        _restore_stubs(saved)
    module.__dict__["_ymdl"] = module.yt_dlp.YoutubeDL
    return module


class _FakeYoutubeDL:
    captured_opts = None
    captured_download = None
    instances = 0

    def __init__(self, opts):
        type(self).captured_opts = opts
        type(self).instances += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=True):
        type(self).captured_download = download
        base = {
            "id": "BV1test",
            "title": "example",
            "duration": 128,
            "thumbnail": "https://example.invalid/t.jpg",
        }
        if download:
            return {**base, "ext": "m4a"}
        # 只取元信息时 yt-dlp 会给 ext=None
        return {**base, "ext": None}


class BilibiliMetadataOnlyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.module = _load_bilibili_downloader()
        except Exception as exc:  # pragma: no cover - env without yt-dlp
            raise unittest.SkipTest(f"bilibili_downloader not importable: {exc}")

    def setUp(self):
        self.module.yt_dlp.YoutubeDL = _FakeYoutubeDL
        _FakeYoutubeDL.captured_opts = None
        _FakeYoutubeDL.captured_download = None
        _FakeYoutubeDL.instances = 0

    def tearDown(self):
        self.module.yt_dlp.YoutubeDL = self.module.__dict__["_ymdl"]

    def test_skip_download_tolerates_missing_formats(self):
        self.module.BilibiliDownloader().download(
            "https://www.bilibili.com/video/BV1test", output_dir="/tmp", skip_download=True
        )
        opts = _FakeYoutubeDL.captured_opts
        self.assertTrue(opts.get("skip_download"))
        self.assertTrue(opts.get("ignore_no_formats_error"))

    def test_skip_download_does_not_request_media(self):
        self.module.BilibiliDownloader().download(
            "https://www.bilibili.com/video/BV1test", output_dir="/tmp", skip_download=True
        )
        self.assertIs(_FakeYoutubeDL.captured_download, False)

    def test_missing_ext_falls_back_to_m4a(self):
        result = self.module.BilibiliDownloader().download(
            "https://www.bilibili.com/video/BV1test", output_dir="/tmp", skip_download=True
        )
        self.assertTrue(result.file_path.endswith(".m4a"), result.file_path)
        self.assertNotIn("None", result.file_path)
        self.assertIsNone(result.video_path)

    def test_full_download_still_selects_an_audio_format(self):
        result = self.module.BilibiliDownloader().download(
            "https://www.bilibili.com/video/BV1test", output_dir="/tmp"
        )
        opts = _FakeYoutubeDL.captured_opts
        self.assertIn("bestaudio", opts.get("format", ""))
        self.assertNotIn("ignore_no_formats_error", opts)
        self.assertIs(_FakeYoutubeDL.captured_download, True)
        self.assertTrue(result.file_path.endswith(".mp3"), result.file_path)


def _download_signature(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "download":
            names = [arg.arg for arg in node.args.args]
            defaults = {
                arg.arg: ast.unparse(default)
                for arg, default in zip(node.args.args[-len(node.args.defaults):], node.args.defaults)
            }
            used = [
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and child.id == "skip_download"
            ]
            return names, defaults, len(used)
    return None, None, 0


class DownloaderInterfaceTest(unittest.TestCase):
    # download() 里真正使用 skip_download 的次数下限（参数本身是 ast.arg，不计入）。
    # 只剩 bilibili：其余平台的下载器已随 spec 005 的死代码清理删除。
    MIN_USES = {"bilibili": 1}

    def test_every_platform_accepts_skip_download(self):
        for platform, path in PLATFORM_MODULES.items():
            with self.subTest(platform=platform):
                names, defaults, used = _download_signature(path)
                self.assertIsNotNone(names, f"{platform}: 找不到 download()")
                self.assertIn("need_video", names)
                self.assertIn("skip_download", names)
                self.assertEqual(defaults.get("skip_download"), "False")
                self.assertGreaterEqual(used, self.MIN_USES[platform], f"{platform}: skip_download 参数没有被真正使用")


if __name__ == "__main__":
    unittest.main()
