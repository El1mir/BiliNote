import os
import sys
from pathlib import Path

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


def _backend_root() -> str:
    """开发态的 backend 目录；冻结态就是 exe 所在目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))


def get_data_dir() -> str:
    """统一的媒体数据根目录（spec 022 D4）。

    规则：
    - DATA_DIR 是绝对路径：直接用；
    - DATA_DIR 是相对路径：相对 backend 解析（与「cd backend && python main.py」
      的工作目录语义一致，但不再依赖进程 cwd）；
    - 未设置：<backend>/data（冻结态 <exe_dir>/data）。

    历史 bug（R3）：这里曾把 base 取成 <backend>/data 后又拼一次 data，
    返回 <backend>/data/data，而下载器、导出、媒体登记分别按 <backend>/data
    解析——媒体资源登记因「路径越界」全部失败。现在只在这一处定义根目录。
    """
    base = _backend_root()
    configured = (os.getenv("DATA_DIR") or "").strip()
    if configured:
        path = (
            configured
            if os.path.isabs(configured)
            else os.path.join(base, configured)
        )
    else:
        path = os.path.join(base, "data")
    path = os.path.abspath(path)
    os.makedirs(path, exist_ok=True)
    return path


def get_model_dir(subdir: str = "whisper") -> str:
    # 判断是否为打包状态（PyInstaller）
    if getattr(sys, 'frozen', False):
        # exe 执行，放在 APPDATA 或 ~/.cache 下
        base_dir = os.path.join(os.getenv("APPDATA") or str(Path.home()), "BiliNote", "models")
    else:
        # 开发时，相对项目根目录
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models"))

    path = os.path.join(base_dir, subdir)
    os.makedirs(path, exist_ok=True)
    return path


def get_app_dir(subdir: str = "") -> str:
    """
    返回一个稳定的可写目录：
    - 开发时：使用项目 data 目录
    - 打包后：使用 exe 所在目录
    """
    if getattr(sys, 'frozen', False):
        # 打包后运行：使用 main.exe 所在目录
        base_dir = os.path.dirname(sys.executable)
    else:
        # 开发模式：使用项目的 /data 目录
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))

    full_path = os.path.join(base_dir, subdir)
    os.makedirs(full_path, exist_ok=True)
    return full_path