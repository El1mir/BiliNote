import shutil
from pathlib import Path

from dotenv import load_dotenv
import subprocess
import os
import uuid
load_dotenv()
api_path = os.getenv("API_BASE_URL", "http://localhost")
BACKEND_PORT= os.getenv("BACKEND_PORT", 8483)

BACKEND_BASE_URL = f"{api_path}:{BACKEND_PORT}"

from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 截图/抽帧类 ffmpeg 调用的上限。视频损坏、路径是网络盘、或 ffmpeg 等着读
# 标准输入时都会永久阻塞，而调用方（ThreadPoolExecutor.map）会把整个任务挂死。
_FFMPEG_TIMEOUT_SECONDS = 60


def generate_screenshot(video_path: str, output_dir: str, timestamp: int, index: int) -> str:
    """
    使用 ffmpeg 生成截图，返回生成图片路径
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"screenshot_{index:03}_{uuid.uuid4()}.jpg"
    output_path = output_dir / filename

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",   # 静音：截图失败靠 returncode 判断，不刷屏
        "-nostats",
        "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]

    logger.debug("Running command: %s", command)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        # 没有 timeout 时这里会**永久**阻塞，而调用方是 executor.map，
        # 于是整个任务无日志卡死（真机排障时极难定位）。超时就当失败返回，
        # 交给上层的「生成截图失败」分支统一处理。
        logger.error(
            "ffmpeg 截图超时（超过 %ss，ts=%s）：%s",
            _FFMPEG_TIMEOUT_SECONDS,
            timestamp,
            (video_path or ""),
        )
        return ""

    if result.returncode != 0:
        logger.error("ffmpeg 截图失败 (ts=%s): %s", timestamp, (result.stderr or "").strip())

    return str(output_path)



def save_cover_to_static(local_cover_path: str, subfolder: Optional[str] = "cover") -> str:
    """
    将封面图片保存到 static 目录下，并返回前端可访问的路径
    :param local_cover_path: 本地原封面路径（比如提取出来的jpg）
    :param subfolder: 子目录，默认是 cover，可以自定义
    :return: 前端访问路径，例如 /static/cover/xxx.jpg
    """
    # 项目根目录
    project_root = os.getcwd()

    # static目录
    static_dir = os.path.join(project_root, "static")

    # 确定目标子目录
    target_dir = os.path.join(static_dir, subfolder or "cover")
    os.makedirs(target_dir, exist_ok=True)

    # 拷贝文件
    file_name = os.path.basename(local_cover_path)
    target_path = os.path.join(target_dir, file_name)
    shutil.copy2(local_cover_path, target_path)  # 保留原时间戳、权限
    image_relative_path = f"/static/{subfolder}/{file_name}".replace("\\", "/")
    url_path = f"{BACKEND_BASE_URL.rstrip('/')}/{image_relative_path.lstrip('/')}"
    # 返回前端可访问的路径
    return url_path
