from pydantic import AnyUrl, validator, BaseModel, field_validator, model_validator
import re
from urllib.parse import urlparse

from app.utils.url_parser import normalize_video_url, parse_bilibili_collection_url

#: 真正能生成笔记的平台。**必须与** `app/services/constant.py` 的
#: `SUPPORT_PLATFORM_MAP` **保持一致**：那里只管实例化哪个 downloader，这里管
#: 链接入口放不放行。两者脱节的后果是用户提交一个能过校验、到了流水线里才
#: `PLATFORM_NOT_SUPPORTED` 的链接 —— 白等一次排队。
#:
#: 2026-10-05 收口：youtube / douyin / kuaishou 的 downloader 已随死代码清理删除，
#: 对应的识别规则也一并下线。
SUPPORTED_PLATFORMS = {
    "bilibili": r"(https?://)?(www\.)?bilibili\.com/video/[a-zA-Z0-9]+",
}


def is_supported_video_url(url: str) -> bool:
    parsed = urlparse(url)

    # 检查是否为Bilibili的短链接
    if parsed.netloc == "b23.tv":
        return True

    # B 站合集 / 系列（space.bilibili.com/{mid}/lists/{sid} 等）
    if parse_bilibili_collection_url(url):
        return True

    return any(re.match(pattern, url) for pattern in SUPPORTED_PLATFORMS.values())


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
