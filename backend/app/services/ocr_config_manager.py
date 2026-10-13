"""OCR 辅助模式的配置管理（spec 008 ticket 01）。

与 `TranscriberConfigManager` 同构：独立 JSON 文件、独立读写方法、不动数据库表。
配置文件默认 `config/ocr.json`。

已收敛为智谱专用（2026-10-04 真机验证后）
----------------------------------------
原先这里是通用双协议（`layout_parsing` + `openai_chat`），代价是七个底层字段要暴露给
用户。真机验证之后端点、鉴权、字段名、响应路径全部已实测确认，没有不确定性需要靠配置兜，
而这些字段用户根本看不懂。所以现在只保留**真正需要用户填**的四个字段
（`enabled` / `base_url` / `api_key` / `model_name`），其余全部是模块常量：

  * 端点路径   → :data:`ENDPOINT_PATH`
  * 鉴权头形态 → :data:`AUTH_SCHEME`
  * 文件字段名 → :data:`FILE_FIELD`
  * 响应取值   → :data:`RESPONSE_PATH`

`base_url` 之所以仍然可配：国内站（`open.bigmodel.cn`）与国际站（`api.z.ai`）确实不同，
自建网关的路径前缀也可能不同。它是唯一真正会因部署而变的字段。

旧配置兼容：`_normalize` 仍然读得懂旧文件里的 `protocol` / `endpoint_path` 等键
（读时忽略、不报错），所以升级后不会把老用户的配置判成损坏；写入时不再落这些键。

关于「页数上限」默认取 30
------------------------
ticket 01 要求在国内文档（100 页）与国际文档（30 页）的矛盾中**取小值**作为默认护栏。
后续调研（两条独立子代理交叉印证）认为「国际站 30 页」的说法找不到一手来源，
两边实际都是 100。这里仍然按 ticket 的字面要求默认 30：这是**保守护栏**，
且本功能实际只处理抽出的单帧图片（非 PDF），不会误伤主流程；
需要处理多页 PDF 时可在设置页调大。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------- 智谱专用常量（不再是配置项） ----------------
#
# 这些值都经过真机验证（2026-10-04，真实截图 + 完整 key）：
#   POST https://open.bigmodel.cn/api/paas/v4/layout_parsing
#   Authorization: Bearer <id>.<secret>
#   body: {"model":"glm-ocr","file":"data:<mime>;base64,...", ...}
#   响应: {"md_results": "<markdown>", "layout_details": [[{label,content,...}]]}
# 全部与下面的常量一致。

# 服务基地址：仅作为「新建时」的占位提示，用户可改成国际站或自建网关
DEFAULT_BASE_URL = "https://open.bigmodel.cn"

DEFAULT_MODEL_NAME = "glm-ocr"

# 版面解析端点路径，拼在 base_url 之后
ENDPOINT_PATH = "/api/paas/v4/layout_parsing"

# 鉴权头形态：`Authorization: {AUTH_SCHEME}{api_key}`。
# 真机同时验证过裸 key 也能通，但官方 OpenAPI 明确声明 security: bearerAuth，
# 所以按文档走 Bearer。
AUTH_SCHEME = "Bearer "

# 请求体里承载文件的字段名
FILE_FIELD = "file"

# 响应里取 Markdown 文本的路径（点分，数字段按列表下标解释）
RESPONSE_PATH = "md_results"

DEFAULT_TIMEOUT = 300  # 秒；多页 PDF 要放宽（厂商 SDK 亦暴露 GLMOCR_TIMEOUT=600）
DEFAULT_MAX_FILE_MB = 10  # 图片上限；PDF 是 50MB，但本功能只发单帧图片
DEFAULT_MAX_PAGES = 30  # 保守护栏，见模块 docstring

# 真正需要用户填的字段（其余都是上面的常量）
#
# 注意：`api_key` 在 `ENV_FALLBACK_FIELDS` 里可以用环境变量兜底，
# 但这里仍然列出——它是配置的一部分，只是来源可以是环境变量。
CONFIG_FIELDS = (
    "enabled",
    "base_url",
    "api_key",
    "model_name",
    "timeout",
    "max_file_mb",
    "max_pages",
)


def normalize_base_url(value: Any) -> str:
    """把用户填的服务地址收敛成 requests 能识别的绝对 URL。

    现实里最常见的两种填法都会让 `requests` 直接抛
    `InvalidSchema: No connection adapters were found`：
      - `open.bigmodel.cn`（漏了 `https://`）→ 缺 scheme；
      - `ttps://open.bigmodel.cn`（手滑漏了 h）→ scheme 不是 http/https。

    这里只做「修」不做事后报错：缺 scheme 就补 `https://`，写成 `ttps://`/`ttp://`
    这类明显的手滑就补齐成 `https://`/`http://`。真实存在的其它 scheme（file、ftp 等）
    原样返回，交给上层校验去拦，避免把用户的意图改得面目全非。
    """
    text = str(value or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    for typo, fixed in (("ttps://", "https://"), ("ttp://", "http://")):
        if lowered.startswith(typo):
            return fixed + text[len(typo):]

    if "://" not in text:
        return "https://" + text

    return text


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "是")


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mask_key(key: Optional[str]) -> str:
    """API Key 打码，规则与 ProviderService.mask_key / TranscriberConfigManager 保持一致。"""
    if not key:
        return ""
    key = str(key)
    if len(key) < 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


class OcrConfigManager:
    """管理 OCR 辅助配置，存储在 JSON 文件中，支持前端动态修改。"""

    def __init__(self, filepath: str = "config/ocr.json"):
        # 相对路径一律按 `backend/` 解析（本文件在 backend/app/services/ 下，
        # 上溯三层即 backend/）。默认值是相对路径，而它是否生效**取决于进程
        # 的当前工作目录**：uvicorn 从 backend/ 启动时没问题，但一旦换个启动
        # 方式或从仓库根跑脚本，配置就会静默读成空——
        # base_url / model_name 全空，报错却指向「未配置」，极具误导性。
        raw_path = Path(filepath)
        if not raw_path.is_absolute():
            raw_path = Path(__file__).resolve().parents[2] / raw_path
        self.path = raw_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- 底层读写 ----------------

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write(self, data: Dict[str, Any]):
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------------- 归一化与校验 ----------------

    @staticmethod
    def _normalize(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """补齐缺省字段，保证前端/客户端拿到结构一致的 dict。

        数值型护栏只在「缺失」时补默认值——0 或非法值要留给 `_validate` 报错，
        不能悄悄被 `or` 吞成默认值（`TranscriberConfigManager` 踩过这个坑）。
        """
        raw = raw or {}

        # 旧配置里的 protocol / endpoint_path / response_path / auth_scheme /
        # file_field / prompt / extra_params 一律**读时忽略**：
        # 这些概念已经从产品里移除，但老文件里还留着它们。
        # 不报错、不迁移、也不写入（见 _write 只用 CONFIG_FIELDS），
        # 这样升级不会把老用户的配置判成损坏。

        timeout = raw.get("timeout")
        if timeout is None or timeout == "":
            timeout = DEFAULT_TIMEOUT

        max_file_mb = raw.get("max_file_mb")
        if max_file_mb is None or max_file_mb == "":
            max_file_mb = DEFAULT_MAX_FILE_MB

        max_pages = raw.get("max_pages")
        if max_pages is None or max_pages == "":
            max_pages = DEFAULT_MAX_PAGES

        return {
            "enabled": _as_bool(raw.get("enabled"), False),
            "base_url": normalize_base_url(raw.get("base_url")),
            "api_key": str(raw.get("api_key") or ""),
            "model_name": str(raw.get("model_name") or "").strip(),
            "timeout": timeout,
            "max_file_mb": max_file_mb,
            "max_pages": max_pages,
        }

    @staticmethod
    def _validate(cfg: Dict[str, Any]):
        """校验待写入的配置。

        必填字段只在**启用**时校验——未启用时允许留空，用户可以先填一半先存着。
        """
        if not _as_bool(cfg.get("enabled")):
            return

        for field, label in (
            ("base_url", "服务地址"),
            ("api_key", "API Key"),
            ("model_name", "模型名"),
        ):
            if not str(cfg.get(field) or "").strip():
                raise ValueError(f"启用 OCR 辅助时，{label}不能为空")

        # 先转换再比较：`cfg.get(...)` 可能是 None，直接塞进 int() 既会抛错也不利于类型检查
        try:
            timeout = int(cfg.get("timeout") or 0)
        except (TypeError, ValueError):
            raise ValueError("超时时间必须为正整数") from None
        if timeout <= 0:
            raise ValueError("超时时间必须为正整数")

        try:
            max_file_mb = float(cfg.get("max_file_mb") or 0)
        except (TypeError, ValueError):
            raise ValueError("单文件大小上限必须为正数") from None
        if max_file_mb <= 0:
            raise ValueError("单文件大小上限必须为正数")

        try:
            max_pages = int(cfg.get("max_pages") or 0)
        except (TypeError, ValueError):
            raise ValueError("页数上限必须为正整数") from None
        if max_pages <= 0:
            raise ValueError("页数上限必须为正整数")


    # ---------------- 对外接口 ----------------

    # 允许通过 update_config 修改的字段。
    # 与模块级 :data:`CONFIG_FIELDS` 同源——协议抽象相关的 7 个字段已移除。
    EDITABLE_FIELDS = CONFIG_FIELDS

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置（api_key 为明文，仅供后端内部使用）。"""
        return self._normalize(self._read())

    def get_public_config(self) -> Dict[str, Any]:
        """给前端的版本：api_key 打码，避免明文回传。"""
        cfg = self.get_config()
        cfg["api_key"] = _mask_key(cfg.get("api_key"))
        # 顺带把「默认值」告诉前端，便于占位提示与「恢复默认」按钮。
        # 现在都是扁平字符串/数字（协议抽象已移除）。
        cfg["_defaults"] = {
            "base_url": DEFAULT_BASE_URL,
            "model_name": DEFAULT_MODEL_NAME,
            "timeout": DEFAULT_TIMEOUT,
            "max_file_mb": DEFAULT_MAX_FILE_MB,
            "max_pages": DEFAULT_MAX_PAGES,
        }
        return cfg

    def update_config(self, **fields) -> Dict[str, Any]:
        """更新配置并持久化。

        前端回显的是打码后的 key，含 `*` 视为「未改动」，直接丢弃该字段，
        绝不能把掩码值存进去覆盖真实密钥（`ProviderService.update_provider` 踩过这个坑）。
        """
        data = self._read()
        current = self._normalize(data)

        for key in self.EDITABLE_FIELDS:
            if key not in fields:
                continue
            value = fields[key]
            if value is None:
                continue
            if key == "api_key" and "*" in str(value):
                continue
            current[key] = value

        # 先校验再归一化：`_normalize` 会把未知协议悄悄改成默认值，
        # 那样用户在设置页选错协议只会「保存成功但行为不对」，很难排查。
        self._validate(current)
        normalized = self._normalize(current)
        self._write(normalized)
        return normalized

    def resolve_endpoint_path(self, cfg: Optional[Dict[str, Any]] = None) -> str:
        """返回实际要请求的路径。

        保留方法名是为了不动调用方；现在没有协议分支，直接返回常量。
        """
        return ENDPOINT_PATH

    def resolve_response_path(self, cfg: Optional[Dict[str, Any]] = None) -> str:
        """响应里 Markdown 的位置。同上，现在是常量。"""
        return RESPONSE_PATH

    def is_ready(self) -> Dict[str, Any]:
        """OCR 辅助是否就绪可用。

        返回 {ready, enabled, model_name, reason}，与
        `TranscriberConfigManager.is_model_ready()` 同构，供生成流程做门禁。

        语义（spec 008 §5.5 / ticket 02 §5）：
          - `enabled=False` → ready=True 且 enabled=False，走原路径，不算失败；
          - `enabled=True` 但缺配置 → ready=False，任务应直接失败并指向设置页。
        """
        cfg = self.get_config()
        result = {
            "ready": True,
            "enabled": bool(cfg.get("enabled")),
            "model_name": cfg.get("model_name"),
            "reason": "",
        }

        if not result["enabled"]:
            return result

        missing = [
            label
            for field, label in (
                ("base_url", "服务地址"),
                ("api_key", "API Key"),
                ("model_name", "模型名"),
            )
            if not str(cfg.get(field) or "").strip()
        ]
        if missing:
            result["ready"] = False
            result["reason"] = (
                "OCR 辅助已启用但配置不完整（缺少：" + "、".join(missing) + "），"
                "请先在「设置 → OCR 辅助」补全"
            )
        return result

    # ---------------- 环境变量兜底 ----------------

    def get_config_with_env_fallback(self) -> Dict[str, Any]:
        """允许用环境变量提供密钥，便于容器部署时不把 key 写进 JSON。

        `OCR_API_KEY` / `OCR_BASE_URL` / `OCR_MODEL_NAME` 只在 JSON 里对应字段为空时生效。
        """
        cfg = self.get_config()
        if not cfg.get("api_key"):
            cfg["api_key"] = os.getenv("OCR_API_KEY", "")
        if not cfg.get("base_url"):
            cfg["base_url"] = os.getenv("OCR_BASE_URL", "")
        if not cfg.get("model_name"):
            cfg["model_name"] = os.getenv("OCR_MODEL_NAME", "")
        return cfg
