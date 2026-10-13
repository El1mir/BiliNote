# -*- coding: utf-8 -*-
"""诊断脚本：直接打智谱 layout_parsing，把鉴权层与请求体层分开验证。

用法（key 从环境变量读，不落盘、不进日志）：
    $env:ZHIPU_API_KEY="..."
    backend\\.venv\\Scripts\\python.exe scripts\\diag_zhipu_ocr.py

它按顺序做四件事，每件都单独报告，目的是**定位 401 到底出在哪一层**：
  1. 打印 key 形态（长度/是否带点/是否 hex32）——不打印 key 本身；
  2. 用一个 1x1 的极小 PNG 打 layout_parsing，看是否仍然 401；
  3. 用同一个 key 打 chat/completions（最基础的鉴权探针），
     如果这里也 401，说明是 key 本身的问题而不是 layout_parsing 特有；
  4. 打印两边的原始响应体，方便比对。
"""

from __future__ import annotations

import os
import sys

import requests

BASE = "https://open.bigmodel.cn"
KEY = os.environ.get("ZHIPU_API_KEY", "").strip()

# 1x1 透明 PNG，足够小，排除体积/编码问题。
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def shape(key: str) -> str:
    if not key:
        return "EMPTY (未设置 ZHIPU_API_KEY)"
    parts = [
        f"len={len(key)}",
        f"has_dot={'.' in key}",
        f"parts={len(key.split('.'))}",
        f"hex32={bool(__import__('re').fullmatch(r'[0-9a-fA-F]{32}', key))}",
        f"prefix={key[:4]}",
    ]
    return " ".join(parts)


def probe(name: str, url: str, headers: dict, payload: dict) -> None:
    print(f"\n{'=' * 70}\n[{name}] POST {url}")
    print(
        f"[{name}] Authorization scheme = {headers.get('Authorization', '<none>')[:16]}..."
    )
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        print(f"[{name}] REQUEST FAILED: {exc}")
        return
    print(f"[{name}] HTTP {r.status_code}")
    body = r.text
    print(f"[{name}] body[:600] = {body[:600]}")


def main() -> int:
    print("Zhipu OCR auth diagnostic")
    print(f"key shape: {shape(KEY)}")
    if not KEY:
        print("\n设置 ZHIPU_API_KEY 后重跑。")
        return 2

    bearer = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

    # --- 探针 3：最基础的鉴权探针（小模型、极短 prompt、不花钱） ---
    probe(
        "chat/completions (auth probe)",
        f"{BASE}/api/paas/v4/chat/completions",
        bearer,
        {
            "model": "glm-4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        },
    )

    # --- 探针 2：layout_parsing，data URI 形态 ---
    probe(
        "layout_parsing (data uri)",
        f"{BASE}/api/paas/v4/layout_parsing",
        bearer,
        {
            "model": "glm-ocr",
            "file": f"data:image/png;base64,{TINY_PNG_B64}",
            "return_crop_images": False,
            "need_layout_visualization": False,
        },
    )

    # --- 探针 2b：同一个 key，但不带 Bearer（有的文档页省略 Bearer） ---
    probe(
        "layout_parsing (raw key, no Bearer)",
        f"{BASE}/api/paas/v4/layout_parsing",
        {"Authorization": KEY, "Content-Type": "application/json"},
        {
            "model": "glm-ocr",
            "file": f"data:image/png;base64,{TINY_PNG_B64}",
            "return_crop_images": False,
        },
    )

    print(f"\n{'=' * 70}\n诊断结束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
