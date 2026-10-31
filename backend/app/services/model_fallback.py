"""LLM 模型列表的归一化工具。

/v1/models 的返回形态在真实世界里并不统一：openai SDK 给 SyncPage，
自建 OpenAI 兼容网关给 list，旧代码在失败时还会返回裸 []。这里把它们收敛成
同一份 [{id, object, owned_by, ...}]，调用方不必再猜。

内置供应商清单（builtin_providers.json）已随内置供应商一并移除：
供应商与模型现在完全由用户在设置页维护，没有假装成功的兜底。
"""
from typing import Any, List

# builtin_providers.json 与本文件同属 backend/app 下：app/services/ -> app/db/


def normalize_models(raw: Any) -> List[dict]:
    """把 SDK 返回值统一成 [{'id', 'object', 'owned_by', ...}] 列表。

    兼容三种形态：
      - openai SDK 的 SyncPage（取 .data）
      - 普通 list（含旧代码失败时返回的 []，绝不能再 .data）
      - list 里既可能是 pydantic Model 也可能是 dict
    """
    if raw is None:
        return []
    data = getattr(raw, "data", raw)  # SyncPage -> .data；list/tuple 原样
    if not isinstance(data, (list, tuple)):
        return []
    out: List[dict] = []
    for m in data:
        if isinstance(m, dict):
            d = m
        elif hasattr(m, "model_dump"):
            d = m.model_dump()
        elif hasattr(m, "dict"):
            d = m.dict()
        else:
            d = {"id": getattr(m, "id", None)}
        if d.get("id"):
            out.append(d)
    return out


def as_model_dicts(model_ids: List[str], owned_by: str = "") -> List[dict]:
    """把模型名列表包成与 SDK Model 一致的 dict，前端下拉直接复用同一套渲染。"""
    return [
        {"id": mid, "object": "model", "created": None, "owned_by": owned_by}
        for mid in model_ids
    ]
