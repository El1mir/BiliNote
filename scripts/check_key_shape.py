# -*- coding: utf-8 -*-
"""证明当前配置里的 key 连「拆分」这一步都过不去。

不用来看请求是否发对，只看一件事：官方 SDK 的 generate_token / 客户端构造
都要求 `id, secret = apikey.split(".")`，而这个 key 没有点。
"""

import json
import re
from pathlib import Path

config = json.loads(Path("backend/config/ocr.json").read_text(encoding="utf-8"))
key = str(config.get("api_key") or "")

print(f"key length      = {len(key)}")
print(f"parts by '.'    = {len(key.split('.'))}")
print(f"matches hex32   = {bool(re.fullmatch(r'[0-9a-fA-F]{32}', key))}")
print()

try:
    id_part, secret_part = key.split(".")
    print(f"split OK: id={id_part[:4]}... secret_len={len(secret_part)}")
except ValueError as exc:
    print(f"split FAILED ({exc})  <== 官方 SDK 在这一步就会抛 invalid apikey")

print()
print("expected shape: <32-hex id>.<secret>   (两段，中间一个点)")
print("actual   shape: <32-hex>               (只有第一段，点之后全丢了)")
