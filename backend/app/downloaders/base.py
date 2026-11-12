from abc import ABC, abstractmethod
from typing import Mapping, Optional

from app.enmus.note_enums import DownloadQuality
from app.models.notes_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult
from app.utils.path_helper import get_data_dir

QUALITY_MAP = {"fast": "32", "medium": "64", "slow": "128"}

# yt-dlp 的 `retries` 默认值(10)是命令行参数解析器给的，Python API 不套用它：
# 不显式设置时 HttpFD 拿到的是 `self.params.get('retries')` == None，而
# `RetryManager.__init__` 做的是 `self.retries = _retries or 0`——也就是
# 一次都不重试。任何一次网络抖动（例如 B 站 CDN
# upos-sz-mirror*.bilivideo.com 读超时）都会让整个笔记任务直接失败。
#
# 这里的值偏保守：笔记任务是用户在前台等的，重试太多不如早点失败让用户重来。
#: 兜底值：runtime_limits 读不到时用它（例如测试里把 app 包整个替换成桩）。
_FALLBACK_RETRIES = 3
_FALLBACK_SOCKET_TIMEOUT = 30

class _YdlRetryOpts(Mapping[str, int]):
    """yt-dlp 的重试参数，**每次解包都重新读一次运行时配置**。

    为什么是 Mapping 而不是普通 dict：这两个值（重试次数、socket 超时）已经
    变成「设置 → 通用」里的可配置项，写死成模块级 dict 的话，用户在界面上改完
    还得重启后端才生效。而 dict 子类会被 `**` 的 C 快路径直接读底层存储，
    绕过任何 `__getitem__` 重写 —— 所以这里用不可变的 Mapping 实现。

    读不到运行时配置时回落常量：下载器在测试里常被单独加载（app 包被桩替换），
    那时 import runtime_limits 会失败，不能因此让整个下载器不可用。
    """

    _KEYS = ("retries", "fragment_retries", "socket_timeout")

    def _limits(self):
        try:
            from app.services import runtime_limits

            return runtime_limits
        except Exception:  # noqa: BLE001 - 单独加载 base.py 时 app 包可能不存在
            return None

    def __getitem__(self, key: str) -> int:
        limits = self._limits()
        if key in ("retries", "fragment_retries"):
            if limits is None:
                return _FALLBACK_RETRIES
            return int(limits.download_retries())
        if key == "socket_timeout":
            if limits is None:
                return _FALLBACK_SOCKET_TIMEOUT
            return int(limits.download_socket_timeout_seconds())
        raise KeyError(key)

    def __iter__(self):
        return iter(self._KEYS)

    def __len__(self) -> int:
        return len(self._KEYS)

YDL_RETRY_OPTS: Mapping[str, int] = _YdlRetryOpts()


class Downloader(ABC):
    def __init__(self):
        # TODO 需要修改为可配置
        self.quality = QUALITY_MAP["fast"]
        # spec 022 D4：与下载落盘、媒体登记共用同一个数据根。
        self.cache_data = get_data_dir()

    @abstractmethod
    def download(
        self,
        video_url: str,
        output_dir: str | None = None,
        quality: DownloadQuality = DownloadQuality.fast,
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        """

        :param need_video:
        :param video_url: 资源链接
        :param output_dir: 输出路径 默认根目录data
        :param quality: 音频质量 fast | medium | slow
        :return:返回一个 AudioDownloadResult 类
        """
        raise NotImplementedError

    def download_video(
        self, video_url: str, output_dir: str | None = None
    ) -> str:
        raise NotImplementedError

    def download_subtitles(
        self, video_url: str, output_dir: str | None = None, langs: list | None = None
    ) -> Optional[TranscriptResult]:
        """
        尝试获取平台字幕（人工字幕或自动生成字幕）

        :param video_url: 视频链接
        :param output_dir: 输出路径
        :param langs: 优先语言列表，如 ['zh-Hans', 'zh', 'en']
        :return: TranscriptResult 或 None（无字幕时）
        """
        return None
