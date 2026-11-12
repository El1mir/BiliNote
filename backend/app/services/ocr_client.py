"""OCR 辅助模式的调用层（spec 008 ticket 01）。

唯一路径：智谱 glm-ocr 版面解析端点
-----------------------------------
``POST {base_url}/api/paas/v4/layout_parsing``，请求体 ``{model, file: <data URI>}``，
响应里 ``md_results`` 是整页 Markdown、``layout_details`` 是逐页版面块。
glm-ocr **不在**智谱对话模型枚举里，走不了 ``/chat/completions``，所以只能走这条专用端点。

原先这里还有一条 OpenAI 兼容的 ``/chat/completions`` 路径（用视觉模型充当 OCR），
已于 2026-10-04 真机验证后删除：端点、鉴权头、字段名、响应路径全部实测确认，
不再需要靠配置兜底，而暴露七个底层字段给用户的代价远大于收益。
详见 `specs/008-ocr-assist-and-legacy-cleanup/tickets/01-api-verification.md`。

配置面收敛成四个字段
-------------------
``enabled`` / ``base_url`` / ``api_key`` / ``model_name``。端点路径、鉴权头形态、
文件字段名、响应取值路径都是 :mod:`app.services.ocr_config_manager` 里的模块常量。
``base_url`` 保留可配是因为国内站（``open.bigmodel.cn``）与国际站（``api.z.ai``）
确实不同，自建网关的前缀也可能不同——它是唯一真正会因部署而变的项。

``timeout`` / ``max_file_mb`` / ``max_pages`` 三项继续可配：它们是与上游限制相关的
真实护栏（单张图片 ≤10MB、超时、PDF 页数），不是部署差异。

关于 ``bbox_2d``
---------------
真机确认是 **0–1 归一化**（响应 markdown 里的 ``bbox=[805,174,1177,517]`` 是像素坐标，
与归一化值一一对应）。:func:`_normalize_bbox` 仍然保留除以 1000 的兜底分支，
以防某个网关返回 0–1000 量纲。
"""
from __future__ import annotations

import base64
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from app.services.ocr_config_manager import (
    AUTH_SCHEME,
    FILE_FIELD,
    OcrConfigManager,
    RESPONSE_PATH,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 扩展名 → MIME。上游只明确写了 JPG/PNG（WebP 从未在文档里出现），
# 但这里不做硬拦截：让请求发出去、由上游返回真实错误，比我们自己猜错格式更有信息量。
_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
}

# 需要 PDF 专属字段（页范围）的后缀
_PDF_SUFFIXES = (".pdf",)

# 原始响应里体积巨大的字段，一律不进 `raw`（否则会带着几百 KB base64 落盘/进日志）
_HEAVY_RAW_KEYS = ("layout_visualization", "crop_images")

# `raw` 里单个字符串值的截断长度
_RAW_STRING_LIMIT = 20000

# 错误正文截断长度，避免把整页 base64 打进日志
_ERROR_BODY_LIMIT = 2000

# 上游错误码 → 给用户看的中文提示。调研自智谱开放平台错误码表。
_CODE_HINTS = {
    "1000": "鉴权失败：API Key 无效或未提供",
    "1001": "鉴权失败：API Key 无效",
    "1003": "鉴权失败：API Key 已过期或权限不足",
    "1113": "账户余额不足",
    "1210": "请求参数无效（常见于 file 字段格式错误或模型名不对）",
    "1211": "模型不存在",
    "1212": "该模型不支持此调用方式",
    "1213": "缺少必填参数",
    "1214": "参数取值非法",
    "1301": "内容被判定为敏感",
}

# 视作「文件太大」的 HTTP 状态码（上游没有专门的错误码，只能按状态码兜底）
_TOO_LARGE_STATUS = (413,)

# 重试不会变好的 HTTP 状态码：认证/授权失败、请求被拒。
# 这些只有在用户改了配置（换 key、改权限）之后才可能成功，
# 自动重试除了重跑一遍昂贵的上游调用之外没有任何作用。
_NON_RETRYABLE_STATUS = (401, 403, 413)

# 重试不会变好的业务错误码：鉴权类 + 参数/模型类。
# 参数写错、模型名错、余额不足、内容被拒，都是「改了才会好」。
_NON_RETRYABLE_CODES = (
    "1000",  # 鉴权失败
    "1001",  # 请求头未收到鉴权参数
    "1003",  # Token 已过期
    "1005",  # 二次认证保护
    "1113",  # 余额不足
    "1210",  # 请求参数无效
    "1211",  # 模型不存在
    "1212",  # 模型不支持此调用方式
    "1213",  # 缺少必填参数
    "1214",  # 参数取值非法
    "1301",  # 内容敏感
)


def _is_non_retryable(status_code: Optional[int], code: Any) -> bool:
    """这个 OCR 错误重试一次会不会有不同结果？

    判据取「改了配置才可能成功」：认证失败、参数/模型错误、余额不足、
    内容被拒、体积超限。网络抖动、5xx、超时**不**在此列——那些重试有意义。
    """
    if status_code is not None and int(status_code) in _NON_RETRYABLE_STATUS:
        return True
    if code is not None and str(code) in _NON_RETRYABLE_CODES:
        return True
    return False

# ---- 重试与全局并发（spec 022 D5） ----------------------------------------
#
# 真机 429 来自「多任务各自开 OCR 线程」的叠加，而不是单任务并发设得高：
# 单任务上限由 ocr_stage_concurrency 控制，但多个任务同时跑时总数仍会翻倍。
# 所以这里再加一道**进程级**信号量，重试则负责吸收短暂的配额抖动。
OCR_MAX_CONCURRENCY_DEFAULT = 4
OCR_MAX_ATTEMPTS = 3
OCR_RETRY_BASE_SECONDS = 0.5
OCR_RETRY_MAX_SLEEP_SECONDS = 30.0

_OCR_SEMAPHORE: Optional[threading.BoundedSemaphore] = None
_OCR_SEMAPHORE_SIZE = 0
_OCR_SEMAPHORE_LOCK = threading.Lock()


def ocr_max_concurrency() -> int:
    """进程级 OCR 并发上限（env OCR_MAX_CONCURRENCY，默认 4）。

    非法值回退默认而不是抛错：这是护栏，不是业务参数，配置写错不该让整个
    OCR 功能不可用。
    """
    try:
        return max(1, int(os.getenv("OCR_MAX_CONCURRENCY", str(OCR_MAX_CONCURRENCY_DEFAULT))))
    except (TypeError, ValueError):
        return OCR_MAX_CONCURRENCY_DEFAULT


def _ocr_semaphore() -> threading.BoundedSemaphore:
    """懒建全局信号量；运行期改了上限就重建（旧持有者仍能正常 release）。"""
    global _OCR_SEMAPHORE, _OCR_SEMAPHORE_SIZE
    size = ocr_max_concurrency()
    with _OCR_SEMAPHORE_LOCK:
        if _OCR_SEMAPHORE is None or _OCR_SEMAPHORE_SIZE != size:
            _OCR_SEMAPHORE = threading.BoundedSemaphore(size)
            _OCR_SEMAPHORE_SIZE = size
        return _OCR_SEMAPHORE


def _is_retryable_ocr_error(exc: "OcrError") -> bool:
    """这个 OCR 错误重试一次有没有意义？

    只重试 429 / 5xx / 超时与连接失败。鉴权、参数、内容被拒、体积超限都在
    OcrError.non_retryable 里被排除——它们只有改了配置才会好。
    """
    if exc.non_retryable:
        return False
    status = exc.status_code
    if status is None:
        # 超时/连接失败被包成「OCR 请求失败：...」；其余无状态码错误不重试。
        return "请求失败" in exc.message
    return int(status) == 429 or int(status) >= 500


def _retry_delay(exc: "OcrError", attempt: int) -> float:
    """本次重试前等多久：上游给了 Retry-After 就听它的，否则指数退避 + 抖动。"""
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            delay = None
        if delay is not None:
            return max(0.0, min(delay, OCR_RETRY_MAX_SLEEP_SECONDS))
    delay = OCR_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
    return min(delay, OCR_RETRY_MAX_SLEEP_SECONDS) + random.uniform(0, 0.25)

# 共享 session 及其懒加载锁
_SHARED_SESSION: Optional[requests.Session] = None
_SHARED_SESSION_LOCK = threading.Lock()


def get_shared_session() -> requests.Session:
    """进程内共享的 ``requests.Session``。

    真机日志里出现过「21 个连接池」，原因就是每次调用拿到的是模块级 ``requests`` 而非
    一个 ``Session``：``requests.post`` 每次都会新建一个 ``Session`` → 新建一个
    ``HTTPAdapter`` → 新建一个 ``urllib3.PoolManager``，连接池与 TLS 握手全部不复用。
    插图流程会用 ThreadPoolExecutor 并发调 OCR，因此这里用双检锁只建一次。

    注意：``requests.Session`` 不是「线程安全」的官方承诺，但普遍可安全并发用于不同请求
    （共享的是连接池与 cookie jar，本功能不用 cookie）。这是本仓库里共享 session 的唯一入口。
    """
    global _SHARED_SESSION
    if _SHARED_SESSION is None:
        with _SHARED_SESSION_LOCK:
            if _SHARED_SESSION is None:
                _SHARED_SESSION = requests.Session()
    return _SHARED_SESSION


class OcrError(RuntimeError):
    """OCR 调用失败。

    ``message`` 面向用户；``detail`` 保留上游原始正文供排查；
    ``code`` / ``status_code`` 便于调用方分流，但**不要**依赖它们做业务判断
    （上游错误形状本身就不统一）。
    """

    def __init__(
        self,
        message: str,
        *,
        detail: str = "",
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status_code = status_code
        self.code = code
        # 上游 Retry-After（秒）；重试等待优先用它，缺失时才走指数退避。
        self.retry_after = retry_after
        # 「重试也不会变好」的错误。调用方（note.generate 的顶层 except）会读取
        # 这个属性并转成 `last_error_non_retryable`，让重试循环立刻停下。
        # 典型就是 401/403：key 不对，只有用户改配置才可能成功，
        # 重试只是把几分钟的 LLM 总结再跑一遍（真机实测 43s→72s→111s）。
        self.non_retryable = _is_non_retryable(status_code, code)

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"code={self.code}")
        if self.status_code:
            parts.append(f"HTTP {self.status_code}")
        if self.detail:
            parts.append(self.detail[:_ERROR_BODY_LIMIT])
        return " | ".join(parts)


@dataclass
class OcrBlock:
    """版面块。

    ``bbox`` 统一归一化到 **0–1**（见 :func:`_normalize_bbox`），拿不到时为 ``None``。

    ``label`` 的语义（已核实，见 tickets/01-api-verification.md）：
    **托管 API 只返回 4 个值** ``{image, text, formula, table}``。自建 SDK 里那 10 个细粒度
    标签（``title``/``figure``/``header``/``seal`` 等）是 PP-DocLayout-V3 的原始输出，会经
    ``pipeline.result_formatter.label_visualization_mapping`` **归并**成这 4 类后才暴露出来。
    所以调用方不需要防 ``chart``/``figure`` 混入。

    ``label == "image"`` 时 ``content`` 恒为 ``null``（键存在、值为 null）——``image`` 区域
    在下游没有对应的识别 prompt，它只留下坐标给调用方裁剪/引用。这正是「这张图 OCR 没有
    给出可用文字」的信号。

    仍然**不做白名单过滤**：上游是自建/中转时可能给出别的 label，硬过滤会把内容丢掉；
    判定统一交给 :meth:`OcrResult.has_usable_text`。
    """

    label: str
    content: str
    bbox: Optional[List[float]] = None
    page: int = 0
    index: int = 0


# 唯一支持的协议名。
#
# `OcrResult.protocol` 字段与若干落盘/日志位置仍在用它，而产品里已经只剩这一条路，
# 所以保留字段但固定成这个常量——删字段的改动面（响应组装、测试、日志）远大于收益。
PROTOCOL_NAME = "layout_parsing"


@dataclass
class OcrResult:
    """统一返回形态（ticket 01 §4）。"""

    markdown: str
    blocks: List[OcrBlock] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    protocol: str = ""
    model_name: str = ""

    @property
    def text(self) -> str:
        """只要文本时用这个：Markdown 为空则退回把版面块拼起来。"""
        if self.markdown.strip():
            return self.markdown.strip()
        return "\n".join(b.content for b in self.blocks if b.content).strip()

    # ``label == "image"`` 的区块上游恒返回 null content（见 OcrBlock 文档），
    # 所以「有没有文字」只能看 text/formula/table 这三类。
    _TEXT_LABELS = ("text", "formula", "table")

    def text_blocks(self, labels: Optional[Tuple[str, ...]] = None) -> List[OcrBlock]:
        """按 label 取有内容的块，默认取 ``text``/``formula``/``table``。"""
        wanted = labels or self._TEXT_LABELS
        return [b for b in self.blocks if b.label in wanted and (b.content or "").strip()]

    def has_usable_text(self) -> bool:
        """OCR 是否真的给出了可用文字。

        这是「该不该把这张图画进笔记」的核心判据：**除了图片本身什么都没读出来**时，
        插图才有意义；一旦读出了公式/表格/正文，就应该把文字回填进笔记而不是贴一张图。

        判据（依 tickets/01-api-verification.md 的核实结论）：

        * 有 ``formula`` 或 ``table`` 块且内容非空 → 可用（这是用户最在意的化学公式/表格）。
        * 只有 ``image`` 块（content 恒为 null）→ **不可用**，必须插图。
        * 没有版面块时只能看正文；把「正文里除了空白什么都不剩」当成
          不可用，避免把一段空响应误判成可用文字。
        """
        if self.text_blocks(("formula", "table")):
            return True
        if self.text_blocks(("text",)):
            return True
        if self.blocks:
            # 只有版面块、但没有任何带文字的块：典型的「整张图就是一个 image 区域」。
            return False
        # 没有版面块时的兜底：去掉空白 / Markdown 图片语法后还剩字符才算读到了文字。
        stripped = self.markdown or ""
        for token in ("![]", "[]", "(", ")", "!", "[", "]"):
            stripped = stripped.replace(token, " ")
        return bool(stripped.strip())


# --------------------------------------------------------------------------- #
# 取值 / 归一化辅助
# --------------------------------------------------------------------------- #


def _safe_int(value: Any, default: int = 0) -> int:
    """宽容地把上游给的值转成 int（上游字段类型不稳，缺字段/给字符串都见过）。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dig(payload: Any, path: str) -> Any:
    """按点分路径取值，数字段按列表下标解释（如 ``choices.0.message.content``）。"""
    cur = payload
    for seg in str(path or "").split("."):
        seg = seg.strip()
        if not seg:
            continue
        if isinstance(cur, list):
            if not seg.lstrip("-").isdigit():
                return None
            idx = _safe_int(seg)
            if idx >= len(cur) or idx < -len(cur):
                return None
            cur = cur[idx]
        elif isinstance(cur, dict):
            if seg not in cur:
                return None
            cur = cur[seg]
        else:
            return None
    return cur


def _coerce_text(value: Any) -> str:
    """把取值结果压成字符串。OpenAI 兼容响应的 content 可能是 content part 列表。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks: List[str] = []
        for item in value:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks).strip()
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text.strip()
    return ""


def _normalize_bbox(raw: Any) -> Optional[List[float]]:
    """把上游的 ``bbox_2d`` 统一归一到 0–1。

    上游对此自相矛盾：国内文档写「Normalized」，官方仓库的 SDK 文档写归一化到 0–1000。
    判定规则：**全部落在 [0, 1000] 且最大值 > 1** 才当成 0–1000 量纲整体除以 1000，
    否则逐个夹紧到 [0, 1]。两种量纲混在一个数组里是坏数据，整体除 1000 会把它压成
    一片接近 0 的值，版面定位会彻底错位且毫无提示——宁可夹紧也不要静默错位。
    真正上线前应在一次真实响应上确认一次。
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        vals = [float(v) for v in raw]
    except (TypeError, ValueError):
        return None
    if max(vals) > 1.0 and min(vals) >= 0.0 and max(vals) <= 1000.0:
        vals = [v / 1000.0 for v in vals]
    return [min(1.0, max(0.0, v)) for v in vals]


def _slim_raw(payload: Any) -> Any:
    """裁掉原始响应里体积巨大的部分（base64 图像等），保证 ``raw`` 可安全落盘/记日志。"""
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for key, value in payload.items():
            if key in _HEAVY_RAW_KEYS:
                out[key] = f"<已省略 {key}>"
                continue
            out[key] = _slim_raw(value)
        return out
    if isinstance(payload, list):
        return [_slim_raw(item) for item in payload]
    if isinstance(payload, str) and len(payload) > _RAW_STRING_LIMIT:
        return payload[:_RAW_STRING_LIMIT] + f"…<已截断，原长 {len(payload)}>"
    return payload


def _mime_for(path: Path) -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def _extract_error(payload: Any, body: str) -> Tuple[Optional[str], str]:
    """从响应体里挖出 (code, message)。

    上游至少有两种形状：``{"error": {"code": "", "message": ""}}`` 与
    平铺的 ``{"code": "1210", "message": "...", "status": 400}``，都要认。
    """
    code: Optional[str] = None
    message = ""

    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            raw_code = err.get("code")
            code = str(raw_code) if raw_code not in (None, "") else None
            message = str(err.get("message") or "").strip()
        elif isinstance(err, str) and err.strip():
            message = err.strip()

        if not message:
            raw_code = payload.get("code")
            if raw_code not in (None, ""):
                code = code or str(raw_code)
            message = str(payload.get("message") or payload.get("msg") or "").strip()

    if not message:
        message = (body or "").strip()[:_ERROR_BODY_LIMIT]
    return code, message


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #


class OcrClient:
    """按一份配置发起一次 OCR 调用。无状态，可安全复用（真机日志里「21 个连接池」就是没有共享 session 造成的）。"""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        *,
        manager: Optional[OcrConfigManager] = None,
        session: Optional[requests.Session] = None,
    ):
        self._manager = manager or OcrConfigManager()
        # 走 env 兜底，便于容器部署时用 OCR_API_KEY 注入而不写进 JSON
        self._config = config if config is not None else self._manager.get_config_with_env_fallback()
        # 必须拿到 requests.Session 而不是模块级 requests：后者每次 post 都新建
        # Session → HTTPAdapter → PoolManager，连接池完全不复用（真机日志里「21 个连接池」）。
        self._session = session or get_shared_session()

    @property
    def session(self) -> requests.Session:
        """当前使用的 ``requests.Session``（便于测试断言复用行为）。"""
        return self._session

    # ---------------- 只读属性 ----------------

    @property
    def config(self) -> Dict[str, Any]:
        return dict(self._config)

    @property
    def model_name(self) -> str:
        return str(self._config.get("model_name") or "")

    # ---------------- 请求拼装 ----------------

    def _endpoint_url(self) -> str:
        base = str(self._config.get("base_url") or "").strip()
        if not base:
            raise OcrError("未配置 OCR 服务地址（base_url），请先在「设置 → OCR 辅助」填写")
        path = self._manager.resolve_endpoint_path(self._config)
        return base.rstrip("/") + "/" + str(path).lstrip("/")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = str(self._config.get("api_key") or "")
        if api_key:
            # 智谱用标准 Bearer（官方 OpenAPI 声明 security: bearerAuth）。
            # AUTH_SCHEME 自带尾空格，所以直接拼。
            headers["Authorization"] = f"{AUTH_SCHEME}{api_key}"
        return headers

    def _timeout(self) -> float:
        try:
            value = float(self._config.get("timeout") or 0)
        except (TypeError, ValueError):
            value = 0.0
        return value if value > 0 else 300.0

    def _file_to_data_uri(self, path: Path) -> str:
        """读文件并编码成 ``data:<mime>;base64,...``。

        **不做任何压缩**（ticket 01 §5）：超限就报错让用户自己决定怎么缩小。
        """
        limit_mb = self._limit_mb()
        if limit_mb > 0:
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > limit_mb:
                raise OcrError(
                    f"图片体积 {size_mb:.2f}MB 超过上限 {limit_mb:g}MB。"
                    "为避免精度损失这里不做自动压缩，请先自行缩小图片，"
                    "或在「设置 → OCR 辅助」调大体积上限"
                )
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{_mime_for(path)};base64,{encoded}"

    def _limit_mb(self) -> float:
        try:
            return float(self._config.get("max_file_mb") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _check_page_limit(self, path: Path):
        """页数护栏只在 PDF 上有意义。

        本功能实际只发抽出来的单帧图片（每个候选帧一张 jpg），永远不会是 PDF，
        所以这里只做「体积」判断；页范围已无从表达（原先靠 ``extra_params`` 传
        ``start_page_id``/``end_page_id``，那个字段随协议抽象一起去掉了）。
        保留这个函数是因为 ``max_pages`` 与 ``max_file_mb`` 仍是设置页可配的护栏，
        将来支持 PDF 时从这里接回去即可。
        """
        if path.suffix.lower() not in _PDF_SUFFIXES:
            return
        max_pages = _safe_int(self._config.get("max_pages"))
        if max_pages <= 0:
            return
        # 拿不到请求页范围就无法判断，直接放过——体积上限仍然在 _file_to_data_uri 里把关。

    def _build_layout_parsing_request(self, path: Path) -> Dict[str, Any]:
        """构造 layout_parsing 请求体。

        真机验证过的形状：``model`` + ``file``（data URI）是必填，其余都可省。
        这里显式关掉两个体积巨大的可选字段——``return_crop_images`` 会让响应带回
        每块裁剪图的 base64（一张图几百 KB），``need_layout_visualization`` 会带回
        整页可视化的 base64。两者本功能都用不到，开着只是白烧带宽与内存。
        """
        return {
            "model": self.model_name,
            FILE_FIELD: self._file_to_data_uri(path),
            "return_crop_images": False,
            "need_layout_visualization": False,
        }

    # ---------------- 响应解析 ----------------

    def _parse_layout_parsing(self, body: Dict[str, Any]) -> OcrResult:
        markdown = _coerce_text(_dig(body, RESPONSE_PATH))
        if not markdown:
            # 兜底：真机确认 md_results 就是整页 Markdown 字符串，但万一上游改名，
            # 直接按同一个名字再试一次，避免「字段名一改功能全废」。
            markdown = _coerce_text(body.get("md_results"))

        return OcrResult(
            markdown=markdown,
            blocks=self._extract_layout_blocks(body),
            raw=_slim_raw(body),
            protocol=PROTOCOL_NAME,
            model_name=self.model_name,
        )

    @staticmethod
    def _extract_layout_blocks(body: Dict[str, Any]) -> List[OcrBlock]:
        """把 ``layout_details`` 摊平成块列表。

        文档类型是 **``object[][]``**（外层是页、内层是该页的元素），但第三方示例里
        也见过平铺的一维数组，所以两种形状都要认。
        """
        raw = body.get("layout_details")
        if not isinstance(raw, list):
            return []

        blocks: List[OcrBlock] = []
        for page_idx, page in enumerate(raw):
            # 平铺形状：元素本身就是 dict
            items = page if isinstance(page, list) else [page]
            for item in items:
                if not isinstance(item, dict):
                    continue
                blocks.append(
                    OcrBlock(
                        label=str(item.get("label") or ""),
                        content=str(item.get("content") or ""),
                        bbox=_normalize_bbox(item.get("bbox_2d")),
                        page=page_idx,
                        index=_safe_int(item.get("index")),
                    )
                )
        return blocks

    # ---------------- 对外入口 ----------------

    def recognize_image(self, image_path: Union[str, Path]) -> OcrResult:
        """对一张本地图片（或 PDF）做一次 OCR，带有限重试。

        spec 022 D5：失败一律抛 :class:`OcrError`（消息面向用户、detail 保留原文），
        但 429 / 5xx / 超时最多重试到 OCR_MAX_ATTEMPTS 次；鉴权、参数、内容被拒
        这类「改了配置才会好」的错误立刻抛。每次尝试占一个进程级 OCR 名额，
        所以多个任务叠加时的真实并发也不会超过 OCR_MAX_CONCURRENCY。
        """
        path = Path(image_path)
        if not path.is_file():
            raise OcrError(f"待识别的文件不存在：{path}")
        if not self.model_name:
            raise OcrError("未配置 OCR 模型名，请先在「设置 → OCR 辅助」填写")

        self._check_page_limit(path)

        attempt = 0
        while True:
            attempt += 1
            try:
                with _ocr_semaphore():
                    return self._recognize_once(path)
            except OcrError as exc:
                if attempt >= OCR_MAX_ATTEMPTS or not _is_retryable_ocr_error(exc):
                    raise
                delay = _retry_delay(exc, attempt)
                logger.warning(
                    "OCR 调用失败（第 %d/%d 次），%.1fs 后重试：%s",
                    attempt,
                    OCR_MAX_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)

    def _recognize_once(self, path: Path) -> OcrResult:
        """单次 OCR 调用；重试与全局名额由 recognize_image 负责。"""
        payload = self._build_layout_parsing_request(path)
        parse = self._parse_layout_parsing

        url = self._endpoint_url()
        logger.info(
            "OCR 调用：model=%s url=%s file=%s",
            self.model_name,
            url,
            path.name,
        )

        try:
            response = self._session.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self._timeout(),
            )
        except requests.RequestException as exc:
            raise OcrError(f"OCR 请求失败：{exc}") from exc

        body_text = response.text or ""
        if response.status_code >= 400:
            raise self._http_error(response.status_code, body_text, response)

        try:
            body = response.json()
        except ValueError as exc:
            raise OcrError(
                "OCR 返回的不是 JSON",
                detail=body_text,
                status_code=response.status_code,
            ) from exc

        if not isinstance(body, dict):
            raise OcrError("OCR 返回结构异常（顶层不是对象）", detail=body_text)

        # 有些网关会用 200 包一个错误体，所以成功路径也要看一眼 code
        code, message = _extract_error(body, "")
        if code and not message and str(body.get("code") or "") not in ("", "0", "200"):
            raise self._http_error(response.status_code, body_text, response)

        result = parse(body)
        if not result.markdown and not result.blocks:
            raise OcrError(
                "OCR 未返回任何文本",
                detail=body_text,
                status_code=response.status_code,
            )
        return result

    def _http_error(
        self, status_code: int, body_text: str, response: Any = None
    ) -> OcrError:
        # 先试 .json()：真实 requests.Response 的 .text 与 .json() 偶尔不一致
        # （字符集猜测、网关包装），只看 .text 会把上游错误原文丢掉。
        # 只给 body_text 直接调用（复现问题、写测试）时也照常工作。
        payload: Any = None
        if response is not None:
            try:
                payload = response.json()
            except Exception:
                payload = None
        if not isinstance(payload, (dict, list)):
            try:
                payload = json.loads(body_text)
            except Exception:
                payload = None
        code, message = _extract_error(payload, body_text)

        hint = _CODE_HINTS.get(str(code)) if code else None
        if status_code in _TOO_LARGE_STATUS:
            hint = hint or "请求体过大，请缩小图片或调低体积上限"

        parts = [f"OCR 调用失败（HTTP {status_code}）"]
        if hint:
            parts.append(hint)
        if message:
            parts.append(message)
        retry_after = None
        if response is not None:
            headers = getattr(response, "headers", None)
            raw_retry_after = headers.get("Retry-After") if headers is not None else None
            if raw_retry_after:
                try:
                    retry_after = float(raw_retry_after)
                except (TypeError, ValueError):
                    retry_after = None
        error = OcrError(
            "：".join([parts[0], "，".join(parts[1:])]) if len(parts) > 1 else parts[0],
            detail=body_text,
            status_code=status_code,
            code=str(code) if code else None,
            retry_after=retry_after,
        )
        if error.non_retryable:
            logger.error(
                "OCR 认证/配置类失败（HTTP %s code=%s），重试不会有帮助：%s",
                status_code,
                error.code,
                error.message,
            )
        return error

    # ---------------- 连接测试 ----------------

    def test_connection(self) -> Dict[str, Any]:
        """用内置最小测试图打通一次真实调用。

        返回 ``{ok, message, ...}``——**无论成败都返回 dict**，把上游原始错误原样带出去，
        便于用户在设置页直接看到「到底哪一步不对」。
        """
        from app.services.ocr_test_image import make_test_image  # 延迟导入，避免无谓依赖

        tmp_path: Optional[Path] = None
        try:
            tmp_path = make_test_image()
            result = self.recognize_image(tmp_path)
            preview = result.text.strip().replace("\n", " ")[:120]
            return {
                "ok": True,
                "message": "连接成功",
                "protocol": result.protocol,
                "model_name": result.model_name,
                "preview": preview,
                "blocks": len(result.blocks),
            }
        except OcrError as exc:
            return {
                "ok": False,
                "message": str(exc),
                "detail": exc.detail,
                "code": exc.code,
                "status_code": exc.status_code,
            }
        except Exception as exc:  # 兜底：绝不让设置页因为一个意外异常而 500
            logger.exception("OCR 连接测试出现未预期异常")
            return {"ok": False, "message": f"连接测试出现未预期异常：{exc}"}
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def build_ocr_client(manager: Optional[OcrConfigManager] = None) -> OcrClient:
    """按当前配置造一个客户端。生成流程里用它，避免各处重复读配置。"""
    return OcrClient(manager=manager)
