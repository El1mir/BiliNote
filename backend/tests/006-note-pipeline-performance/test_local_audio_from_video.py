"""spec 006 ticket 05：复用本地视频提取音轨（省掉第二次完整网络下载）。

场景：需要视频理解时已经下载过 `{video_id}.mp4`，随后要音频时不该再跑一遍
yt-dlp。这里固定：
  * ffmpeg 只做音轨提取（-vn）并按 quality 档位设置码率；
  * 已有 mp3 时不再调用 ffmpeg；
  * ffmpeg 失败抛 RuntimeError（调用方会回退到 yt-dlp）；
  * download(need_video=True) 命中本地视频时完全不碰网络；
  * download_video() 会缓存元信息（标题/时长/封面），复用时不重复请求。
"""
import importlib.util
import logging
import os
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "app" / "downloaders" / "bilibili_downloader.py"


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
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
        DownloadQuality=str,
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

    spec = importlib.util.spec_from_file_location("bilibili_downloader_local", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("bilibili_downloader module spec not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__dict__["_ymdl"] = module.yt_dlp.YoutubeDL
    _restore_stubs(saved)
    return module


class _CompletedProcess:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


class _FfmpegRecorder:
    """替代 subprocess.run：记录命令，并在成功时把输出文件写出来。"""

    def __init__(self, fail=False, prefill=False):
        self.calls = []
        self.fail = fail
        self.prefill = prefill

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.fail:
            return _CompletedProcess(returncode=1, stderr="boom: invalid data")
        with open(cmd[-1], "wb") as fh:
            fh.write(b"mp3")
        return _CompletedProcess()


class _FakeYoutubeDL:
    instances = 0
    captured_opts = None

    def __init__(self, opts):
        type(self).instances += 1
        type(self).captured_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=True):
        info = {
            "id": "BV1test",
            "title": "example",
            "duration": 128,
            "thumbnail": "https://example.invalid/t.jpg",
            "ext": "m4a",
        }
        if download:
            outtmpl = type(self).captured_opts.get("outtmpl", "")
            if outtmpl:
                path = outtmpl % {"id": "BV1test", "ext": "mp4"}
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(b"video")
        return info


class LocalAudioFromVideoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.module = _load_bilibili_downloader()
        except Exception as exc:  # pragma: no cover - env without yt-dlp
            raise unittest.SkipTest(f"bilibili_downloader not importable: {exc}")

    def setUp(self):
        self._real_run = self.module.subprocess.run
        self._real_ydl = self.module.yt_dlp.YoutubeDL
        self.module.yt_dlp.YoutubeDL = _FakeYoutubeDL
        _FakeYoutubeDL.instances = 0
        _FakeYoutubeDL.captured_opts = None

    def tearDown(self):
        self.module.subprocess.run = self._real_run
        self.module.yt_dlp.YoutubeDL = self._real_ydl

    def _downloader(self):
        downloader = self.module.BilibiliDownloader()
        downloader._last_video_info = {
            "id": "BV1test",
            "title": "缓存标题",
            "duration": 128,
            "thumbnail": "https://example.invalid/t.jpg",
        }
        return downloader

    def test_extract_audio_uses_quality_bitrate(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            recorder = _FfmpegRecorder()
            self.module.subprocess.run = recorder
            downloader = self._downloader()

            result = downloader._extract_audio_from_local_video(
                video_path=os.path.join(tmp, "BV1test.mp4"),
                video_id="BV1test",
                quality="slow",
                output_dir=tmp,
            )

        cmd = recorder.calls[0]
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-vn", cmd)
        self.assertEqual(cmd[cmd.index("-b:a") + 1], "128k")
        self.assertTrue(result.file_path.endswith("BV1test.mp3"), result.file_path)
        self.assertEqual(result.title, "缓存标题")
        self.assertEqual(result.duration, 128)
        self.assertEqual(result.video_path, os.path.join(tmp, "BV1test.mp4"))

    def test_existing_mp3_skips_ffmpeg(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "BV1test.mp3")
            with open(audio, "wb") as fh:
                fh.write(b"mp3")
            recorder = _FfmpegRecorder(fail=True)
            self.module.subprocess.run = recorder

            result = self._downloader()._extract_audio_from_local_video(
                video_path=os.path.join(tmp, "BV1test.mp4"),
                video_id="BV1test",
                quality="fast",
                output_dir=tmp,
            )

            self.assertEqual(recorder.calls, [])
            self.assertEqual(result.file_path, audio)

    def test_ffmpeg_failure_raises_with_stderr_tail(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.module.subprocess.run = _FfmpegRecorder(fail=True)

            with self.assertRaises(RuntimeError) as ctx:
                self._downloader()._extract_audio_from_local_video(
                    video_path=os.path.join(tmp, "BV1test.mp4"),
                    video_id="BV1test",
                    quality="fast",
                    output_dir=tmp,
                )

            self.assertIn("boom", str(ctx.exception))

    def test_download_reuses_local_video_without_touching_network(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "BV1test.mp4"), "wb") as fh:
                fh.write(b"video")
            self.module.subprocess.run = _FfmpegRecorder()

            result = self._downloader().download(
                "https://www.bilibili.com/video/BV1test",
                output_dir=tmp,
                need_video=True,
            )

            self.assertEqual(_FakeYoutubeDL.instances, 0, "本地已有视频时不该再走 yt-dlp")
            self.assertTrue(result.video_path.endswith("BV1test.mp4"))
            self.assertTrue(result.file_path.endswith("BV1test.mp3"))

    def test_download_falls_back_to_yt_dlp_when_ffmpeg_fails(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "BV1test.mp4"), "wb") as fh:
                fh.write(b"video")
            self.module.subprocess.run = _FfmpegRecorder(fail=True)

            result = self._downloader().download(
                "https://www.bilibili.com/video/BV1test",
                output_dir=tmp,
                need_video=True,
            )

            self.assertEqual(_FakeYoutubeDL.instances, 1)
            self.assertIn("bestaudio", _FakeYoutubeDL.captured_opts.get("format", ""))
            self.assertTrue(result.file_path.endswith("BV1test.mp3"), result.file_path)

    def test_download_video_caches_metadata_for_reuse(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            downloader = self.module.BilibiliDownloader()

            first = downloader.download_video("https://www.bilibili.com/video/BV1test", tmp)
            second = downloader.download_video("https://www.bilibili.com/video/BV1test", tmp)

            self.assertEqual(_FakeYoutubeDL.instances, 1, "第二次应复用本地视频 + 已缓存元信息")
            self.assertEqual(first, second)
            self.assertEqual((downloader._last_video_info or {}).get("id"), "BV1test")


if __name__ == "__main__":
    unittest.main()
