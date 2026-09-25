from pydantic import AnyUrl, validator, BaseModel, field_validator, model_validator
import re
from urllib.parse import urlparse

from app.utils.url_parser import normalize_video_url, parse_bilibili_collection_url

SUPPORTED_PLATFORMS = {
    "bilibili": r"(https?://)?(www\.)?bilibili\.com/video/[a-zA-Z0-9]+",
    "youtube": r"(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[\w\-]+",
    "douyin": "douyin",
    "kuaishou": "kuaishou"
}


def is_supported_video_url(url: str) -> bool:
    parsed = urlparse(url)

    # 检查是否为Bilibili的短链接
    if parsed.netloc == "b23.tv":
        return True

    # B 站合集 / 系列（space.bilibili.com/{mid}/lists/{sid} 等）
    if parse_bilibili_collection_url(url):
        return True

    for name, pattern in SUPPORTED_PLATFORMS.items():
        if pattern in ["douyin", "kuaishou"]:
            if pattern in url:
                return True
        else:
            if re.match(pattern, url):
                return True
    return False


class VideoRequest(BaseModel):
    url: AnyUrl
    platform: str

    @model_validator(mode="before")
    @classmethod
    def normalize_url(cls, data):
        if isinstance(data, dict) and data.get("platform") == "bilibili" and data.get("url"):
            data["url"] = normalize_video_url(str(data["url"]))
        return data

    @field_validator("url")
    def validate_video_url(cls, v):
        if not is_supported_video_url(str(v)):
            raise ValueError("暂不支持该视频平台或链接格式无效")
        return v
