# 05 · 下载路径冗余消除

- **依赖**：—
- **关联**：spec §4 决策 7–8
- **状态**：已完成

## 目标

一次任务里存在两处纯冗余网络工作，都会直接变成用户等待时间。

## 问题一：有字幕时仍会完整下载音频

`note.py::_download_media()` 在检测到平台字幕时会走「只取元信息」路径：

```python
audio = downloader.download(..., need_video=False, skip_download=True)
```

但 `BilibiliDownloader.download()` / `DouyinDownloader.download()` / `KuaishouDownloader.download()` /
`XiaoyuzhoufmDownload.download()` **没有 `skip_download` 形参**，调用直接 `TypeError`，
被 `except Exception as exc: logger.warning(f"元信息提取失败，将尝试完整下载: {exc}")` 吞掉，
于是照旧下载整个音频文件 —— 字幕本来已经够用。

**改动**：给这些下载器补上与 `youtube_downloader.py:57-71` 一致的语义
（`ydl_opts['skip_download']=True`、`extract_info(download=not skip_download)`、
`ext=None` 时不要拼出 `xxx.None`）。

## 问题二：已经下载了视频，仍为取音频再下一遍网络

需要截图/视频理解时 `_download_media()` 先 `download_video()`（本次实测含 4K 视频下载，
期间还有 CDN 超时重试），随后 `download(need_video=True)` 又跑一次 yt-dlp 音频下载（实测 29.76MiB）。

**改动**：`BilibiliDownloader` 记录 `download_video()` 拿到的 `info`（实例级
`self._last_video_info`）；当 `need_video=True` 且本地已存在 `{video_id}.mp4` 时，
不再发起媒体网络下载，改为本地 ffmpeg 抽音频（`-vn -b:a {QUALITY_MAP[quality]}k`），
元信息优先用缓存的 info，缓存缺失时用一次 `skip_download` 的元信息请求补齐。
任何一步失败都回退到原有网络下载路径。

## 问题三：重复的平台字幕请求

`generate()` 在下载前已经试过一次 `downloader.download_subtitles()`；拿到 `None`（无字幕轨）后
`_get_transcript()` 会**原样再试一次**（B 站路径还会再走一遍更脆弱的 yt-dlp 回退）。

**改动**：`_get_transcript()` 新增 `subtitle_attempted: bool = False`；`generate()` 传 `True`，
命中时直接进入转写，不再重复请求。保留 `_get_transcript()` 单独调用时（其它调用方/测试）的
原有「先试字幕」行为。

## 验收

- 有平台字幕的任务：日志不再出现「元信息提取失败」告警，且没有媒体下载请求。
- 需要视频 + 需要音频的任务：只出现一次媒体网络下载，音频由本地视频抽取。
- 无字幕任务：不再出现两次字幕探测日志（「没有可用字幕轨」只出现一次）。
- 所有回退路径失败时行为与改动前一致（仍能完成任务）。
