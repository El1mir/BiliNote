from app.downloaders.bilibili_downloader import BilibiliDownloader


# Generation adapters are intentionally limited to Bilibili. Platform-neutral
# URL intake remains separate so future adapters can be added without widening
# the active generation surface.
SUPPORT_PLATFORM_MAP = {
    "bilibili": BilibiliDownloader(),
}
