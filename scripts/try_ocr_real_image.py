# -*- coding: utf-8 -*-
"""用真实截图跑一次完整 OCR 链路，验证鉴权与解析都对。

用项目自己的 OcrClient + 配置（不是旁路 requests），所以它验证的是
**产品实际走的那条路**：_headers / _endpoint_url / _build_layout_parsing_request
/ _parse_layout_parsing 全部经过。

图片优先取 backend/static/screenshots 里已有的真实截图；没有再回退到
ocr_test_image.make_test_image() 画的那张 ASCII 测试图。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.ocr_client import build_ocr_client  # noqa: E402
from app.services.ocr_test_image import make_test_image  # noqa: E402


def pick_image() -> tuple[Path, bool]:
    shots = sorted(
        Path("backend/static/screenshots").glob("*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if shots:
        return shots[0], False
    return make_test_image(), True


def main() -> int:
    image, temporary = pick_image()
    print(f"image = {image}  (temporary={temporary})")
    print(f"size  = {image.stat().st_size / 1024:.1f} KB")
    print()

    client = build_ocr_client()
    print(f"protocol = {client.protocol}")
    print(f"model    = {client.model_name}")
    print(f"url      = {client._endpoint_url()}")
    print()

    try:
        result = client.recognize_image(image)
    except Exception as exc:  # noqa: BLE001 - 诊断脚本，要把失败原因原样打出来
        print(f"FAILED: {type(exc).__name__}: {exc}")
        detail = getattr(exc, "detail", "")
        if detail:
            print(f"detail: {detail[:800]}")
        return 1
    finally:
        if temporary:
            image.unlink(missing_ok=True)

    print("OK")
    print(f"markdown chars = {len(result.markdown)}")
    print(f"blocks         = {len(result.blocks)}")
    for block in result.blocks[:10]:
        content = (block.content or "").replace("\n", " ")[:60]
        print(
            f"  label={block.label!r:12} page={block.page} index={block.index} content={content!r}"
        )
    print()
    print("--- markdown head ---")
    print(result.markdown[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
