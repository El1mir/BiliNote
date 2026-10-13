"""生成 OCR 连接测试用的内置测试图（spec 008 ticket 01 §1）。

设置页的「连接测试」按钮需要一张**真实存在**的小图去打一次真实调用，
不能只做 URL 可达性探测——否则「鉴权对不对、模型名对不对、响应能不能解析」
一个都验不出来。这里用 Pillow 现画一张，不往仓库里塞二进制资源。

两个刻意的约束
--------------
1. **只用 ASCII**。``ImageFont.load_default()`` 用的是 Pillow 自带的 Aileron，
   没有 CJK 字形；写中文会渲染成方框，OCR 结果不可读，反而干扰排查。
2. **字号足够大、对比度足够高**。小字体会让视觉模型直接返回空串，
   那时用户看到的是「OCR 未返回任何文本」，会误以为是配置问题。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List, Optional

# 测试图内容：混合字母、数字与符号，任何 OCR 引擎都该能读出至少一部分
_TEST_LINES: List[str] = [
    "OCR TEST 12345",
    "E = mc^2",
    "H2O -> H2 + O2",
]

_IMAGE_SIZE = (900, 340)
_BG_COLOR = (255, 255, 255)
_FG_COLOR = (0, 0, 0)
_FONT_SIZE = 56
_MARGIN_X = 48
_MARGIN_Y = 56
_LINE_GAP = 26


def _load_font(size: int):
    """Pillow ≥10.1 支持给默认字体指定字号；更老的版本只能退回位图默认字体。"""
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_test_image(directory: Optional[Path] = None) -> Path:
    """画一张测试图并返回其路径。**调用方负责删除**。

    失败时抛 :class:`RuntimeError` 并带上可读原因（缺 Pillow、临时目录不可写等），
    由调用方转成给用户看的提示。
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的兜底
        raise RuntimeError(
            "缺少 Pillow 依赖，无法生成 OCR 连接测试图。请在后端环境执行：pip install pillow"
        ) from exc

    image = Image.new("RGB", _IMAGE_SIZE, _BG_COLOR)
    draw = ImageDraw.Draw(image)
    font = _load_font(_FONT_SIZE)

    y = _MARGIN_Y
    for line in _TEST_LINES:
        draw.text((_MARGIN_X, y), line, fill=_FG_COLOR, font=font)
        y += _FONT_SIZE + _LINE_GAP

    target_dir = Path(directory) if directory else Path(tempfile.gettempdir())
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建测试图目录 {target_dir}：{exc}") from exc

    fd, raw_path = tempfile.mkstemp(prefix="bilinote_ocr_test_", suffix=".png", dir=str(target_dir))
    path = Path(raw_path)
    try:
        # mkstemp 已经打开了文件描述符，交给 Pillow 时先关掉，避免 Windows 上占用冲突
        import os

        os.close(fd)
        image.save(path, format="PNG")
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"写入测试图失败：{exc}") from exc

    return path
