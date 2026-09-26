import os
import json
import subprocess
import tempfile
from abc import ABC
from typing import Union, Optional, List

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP, YDL_RETRY_OPTS
from app.downloaders.bilibili_dm_patch import apply_bilibili_dm_img_patch
from app.downloaders.bilibili_subtitle import BilibiliSubtitleFetcher
from app.models.notes_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id
from app.services.cookie_manager import CookieConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Inject the dm_img_* / web_location risk-control params Bilibili's wbi/playurl
# gateway now requires; without them the API path returns HTTP 412. See
# app/downloaders/bilibili_dm_patch.py for details.
apply_bilibili_dm_img_patch()


class BilibiliDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self._cookie_mgr = CookieConfigManager()
        self._cookie = self._cookie_mgr.get('bilibili')
        self._cookiefile = self._write_netscape_cookie_file()
        # download_video() 抓到的元信息缓存：复用本地视频时用它补全标题/时长/封面
        self._last_video_info: Optional[dict] = None

    def _write_netscape_cookie_file(self) -> Optional[str]:
        """将 Cookie 写入 Netscape 格式临时文件，返回文件路径（供 yt-dlp cookiefile 使用）"""
        if not self._cookie:
            logger.warning("B站 Cookie 未配置，下载可能失败")
            return None
        lines = ["# Netscape HTTP Cookie File\n"]
        for pair in self._cookie.split("; "):
            if "=" in pair:
                key, value = pair.split("=", 1)
                lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{key}\t{value}\n")
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.writelines(lines)
        tmp.close()
        logger.info("已生成 B站 Netscape Cookie 文件: %s (条目: %d)", tmp.name, len(lines) - 1)
        return tmp.name

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        """
        下载音频（mp3）。

        :param skip_download: 只提取元信息、不下载媒体文件（用于「已有字幕」的快速路径）。
        :param need_video: 调用方是否需要视频；若本地已有该视频，直接从本地视频提取音轨，
            避免第二次完整网络下载（spec 006 ticket 05）。
        """
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        video_id = extract_video_id(video_url, "bilibili")

        # 复用本地已下载的视频：只做一次 ffmpeg 音轨提取，省掉一次完整网络下载
        if need_video and not skip_download and video_id:
            local_video = os.path.join(output_dir, f"{video_id}.mp4")
            if os.path.exists(local_video):
                try:
                    return self._extract_audio_from_local_video(
                        video_path=local_video,
                        video_id=video_id,
                        quality=quality,
                        output_dir=output_dir,
                    )
                except Exception as exc:
                    logger.warning(f"从本地视频提取音频失败，回退到 yt-dlp 下载: {exc}")

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '64',
                }
            ],
            # 让 yt-dlp 的 ffmpeg 后处理也使用自动多线程；音频转码仍受 CPU/编码器限制。
            'postprocessor_args': ['-threads', '0'],
            'noplaylist': True,
            'quiet': False,
        }

        if skip_download:
            ydl_opts['skip_download'] = True
            # 只取元信息时并不需要媒体流；B站接口偶发只回部分格式，
            # 打开该开关可避免格式选择失败把已经拿到字幕的任务带崩。
            ydl_opts['ignore_no_formats_error'] = True

        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile

        if skip_download:
            logger.info("已有字幕，仅提取视频元信息（不下载音视频）")
        else:
            logger.info("开始 yt-dlp 音频下载与 mp3 转码")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=not skip_download)
            video_id = info.get("id") or video_id
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            if skip_download:
                # skip_download 时 yt-dlp 返回 ext=None，默认值不会生效，避免拼出 "xxx.None"
                ext = info.get("ext") or "m4a"
                audio_path = os.path.join(output_dir, f"{video_id}.{ext}")
            else:
                audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        if skip_download:
            logger.info("视频元信息提取完成：%s", title)
        else:
            logger.info("音频下载与 mp3 转码完成：%s", audio_path)

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
            video_path=None  # ❗音频下载不包含视频路径
        )
    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """

        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        logger.debug("video_url: %s", video_url)
        video_id=extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            # 复用本地视频时，音频结果与笔记头部仍需要标题/时长/封面；
            # 这里只发一次纯元信息请求（不下载媒体流）补齐缓存。
            if not self._last_video_info or self._last_video_info.get("id") != video_id:
                try:
                    self._last_video_info = self._fetch_video_info(video_url)
                except Exception as exc:
                    logger.warning(f"获取视频元信息失败（不影响使用本地视频）: {exc}")
            return video_path

        # 检查是否已经存在


        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'format': 'bv*[ext=mp4]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            self._last_video_info = info
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        return video_path

    def _fetch_video_info(self, video_url: str) -> dict:
        """只请求元信息（不下载媒体流），用于复用本地视频时补全标题/时长/封面。"""
        ydl_opts = {
            **YDL_RETRY_OPTS,
            'skip_download': True,
            'ignore_no_formats_error': True,
            'noplaylist': True,
            'quiet': True,
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(video_url, download=False) or {}

    def _extract_audio_from_local_video(
        self,
        video_path: str,
        video_id: str,
        quality: DownloadQuality,
        output_dir: str,
    ) -> AudioDownloadResult:
        """
        从本地已下载的视频里提取音轨（-vn，不消耗网络流量）。

        :param video_path: 本地视频文件
        :param video_id: 视频 ID（决定输出文件名）
        :param quality: 音频质量档位（对应 QUALITY_MAP 的 kbps）
        :param output_dir: 音频输出目录
        :return: AudioDownloadResult
        """
        audio_path = os.path.join(output_dir, f"{video_id}.mp3")
        bitrate = QUALITY_MAP.get(quality, QUALITY_MAP["fast"])
        if not os.path.exists(audio_path):
            logger.info(f"复用本地视频提取音频：{video_path} -> {audio_path}（{bitrate}k）")
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video_path,
                "-vn",
                "-b:a", f"{bitrate}k",
                "-threads", "0",
                audio_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0 or not os.path.exists(audio_path):
                raise RuntimeError(f"ffmpeg 提取音频失败：{(result.stderr or '').strip()[-400:]}")
        else:
            logger.info(f"本地视频对应的音频已存在，直接复用：{audio_path}")

        info = self._last_video_info or {}
        return AudioDownloadResult(
            file_path=audio_path,
            title=info.get("title"),
            duration=info.get("duration", 0),
            cover_url=info.get("thumbnail"),
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
            video_path=video_path,
        )

    def delete_video(self, video_path: str) -> str:
        """
        删除视频文件
        """
        if os.path.exists(video_path):
            os.remove(video_path)
            return f"视频文件已删除: {video_path}"
        else:
            return f"视频文件未找到: {video_path}"

    def download_subtitles(self, video_url: str, output_dir: str = None,
                           langs: List[str] = None) -> Optional[TranscriptResult]:
        """
        尝试获取B站视频字幕

        :param video_url: 视频链接
        :param output_dir: 输出路径
        :param langs: 优先语言列表
        :return: TranscriptResult 或 None
        """
        # 1) 优先走 B 站官方 player API（直拉，无需下视频；AI 字幕需 SESSDATA cookie）
        try:
            result = BilibiliSubtitleFetcher().fetch_subtitles(video_url)
            if result and result.segments:
                return result
        except Exception as e:
            logger.warning(f"player API 直拉字幕异常，回退到 yt-dlp: {e}")

        # 2) Fallback：原 yt-dlp 路径（更脆弱，遇到签名/Cookie 问题失败概率较高）
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        if langs is None:
            langs = ['zh-Hans', 'zh', 'zh-CN', 'ai-zh', 'en', 'en-US']

        video_id = extract_video_id(video_url, "bilibili")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': langs,
            'subtitlesformat': 'srt/json3/best',  # 支持多种格式
            'skip_download': True,
            'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
            'quiet': True,
        }

        # 通过 CookieConfigManager 注入 B站 Cookie（Netscape cookiefile）
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
            ydl_opts['http_headers'] = {'Referer': 'https://www.bilibili.com'}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                # 查找下载的字幕文件
                subtitles = info.get('requested_subtitles') or {}
                if not subtitles:
                    logger.info(f"B站视频 {video_id} 没有可用字幕")
                    return None

                # 按优先级查找字幕
                detected_lang = None
                sub_info = None
                for lang in langs:
                    if lang in subtitles:
                        detected_lang = lang
                        sub_info = subtitles[lang]
                        break

                # 如果按优先级没找到，取第一个可用的（排除弹幕）
                if not detected_lang:
                    for lang, info_item in subtitles.items():
                        if lang != 'danmaku':  # 排除弹幕
                            detected_lang = lang
                            sub_info = info_item
                            break

                if not sub_info:
                    logger.info(f"B站视频 {video_id} 没有可用字幕（排除弹幕）")
                    return None

                # 检查是否有内嵌数据（yt-dlp 有时直接返回字幕内容）
                if 'data' in sub_info and sub_info['data']:
                    logger.info(f"直接从返回数据解析字幕: {detected_lang}")
                    return self._parse_srt_content(sub_info['data'], detected_lang)

                # 查找字幕文件
                ext = sub_info.get('ext', 'srt')
                subtitle_file = os.path.join(output_dir, f"{video_id}.{detected_lang}.{ext}")

                if not os.path.exists(subtitle_file):
                    logger.info(f"字幕文件不存在: {subtitle_file}")
                    return None

                # 根据格式解析字幕文件
                if ext == 'json3':
                    return self._parse_json3_subtitle(subtitle_file, detected_lang)
                else:
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt_content(f.read(), detected_lang)

        except Exception as e:
            logger.warning(f"获取B站字幕失败: {e}")
            return None

    def _parse_srt_content(self, srt_content: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 SRT 格式字幕内容

        :param srt_content: SRT 字幕文本内容
        :param language: 语言代码
        :return: TranscriptResult
        """
        import re
        try:
            segments = []
            # SRT 格式: 序号\n时间戳\n文本\n\n
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)'
            matches = re.findall(pattern, srt_content, re.DOTALL)

            for match in matches:
                idx, start_time, end_time, text = match
                text = text.strip()
                if not text:
                    continue

                # 转换时间格式 00:00:00,000 -> 秒
                def time_to_seconds(t):
                    parts = t.replace(',', '.').split(':')
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

                segments.append(TranscriptSegment(
                    start=time_to_seconds(start_time),
                    end=time_to_seconds(end_time),
                    text=text
                ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)
            logger.info(f"成功解析B站SRT字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'format': 'srt'}
            )

        except Exception as e:
            logger.warning(f"解析SRT字幕失败: {e}")
            return None

    def _parse_json3_subtitle(self, subtitle_file: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 json3 格式字幕文件

        :param subtitle_file: 字幕文件路径
        :param language: 语言代码
        :return: TranscriptResult
        """
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            segments = []
            events = data.get('events', [])

            for event in events:
                # json3 格式中时间单位是毫秒
                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)

                # 提取文本
                segs = event.get('segs', [])
                text = ''.join(seg.get('utf8', '') for seg in segs).strip()

                if text:  # 只添加非空文本
                    segments.append(TranscriptSegment(
                        start=start_ms / 1000.0,
                        end=(start_ms + duration_ms) / 1000.0,
                        text=text
                    ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)

            logger.info(f"成功解析B站字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'file': subtitle_file}
            )

        except Exception as e:
            logger.warning(f"解析字幕文件失败: {e}")
            return None