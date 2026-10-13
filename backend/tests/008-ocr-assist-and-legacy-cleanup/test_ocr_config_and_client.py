"""spec 008 ticket 01：OCR 配置层 + 调用层的回归测试。

真机验证由用户负责（m00837），所以这里只覆盖**不依赖网络**的确定性行为：
配置读写与掩码、两条协议的请求构造、体积上限、响应解析、错误解析。

这些用例的作用是防腐化：ticket 01 的核心诉求是「字段名/鉴权头/端点路径一律可配，
不得硬编码」，而这类约束一旦被后人改回硬编码，功能在真机上依然「看起来正常」，
只有断言才能挡住。
"""
from __future__ import annotations

from typing import Any

import pytest
import requests

from app.services.ocr_client import (
    OcrBlock,
    OcrClient,
    OcrError,
    _dig,
    _extract_error,
    _normalize_bbox,
)
from app.services.ocr_config_manager import OcrConfigManager


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #

@pytest.fixture
def manager(tmp_path):
    return OcrConfigManager(str(tmp_path / "ocr.json"))


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "frame.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 512)
    return path


def make_config(**overrides):
    config = {
        "enabled": True,
        "base_url": "https://open.bigmodel.cn",
        "api_key": "sk-real-secret-key-1234",
        "model_name": "glm-ocr",
    }
    config.update(overrides)
    return config


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = payload if isinstance(payload, str) else "{}"

    def json(self):
        if isinstance(self._payload, str):
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """记录最后一次请求，便于断言「实际发出去的 body/headers 长什么样」。"""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


# --------------------------------------------------------------------------- #
# 配置层
# --------------------------------------------------------------------------- #

def test_config_roundtrip_masks_api_key(manager):
    manager.update_config(**make_config())
    public = manager.get_public_config()

    assert public["enabled"] is True
    assert public["model_name"] == "glm-ocr"
    # 对外一律打码：既不是明文，也不是空串（空串会让用户以为没保存）
    assert public["api_key"] != "sk-real-secret-key-1234"
    assert "*" in public["api_key"]
    # 明文只在服务端内部可见
    assert manager.get_config()["api_key"] == "sk-real-secret-key-1234"


def test_masked_writeback_does_not_overwrite_real_key(manager):
    manager.update_config(**make_config())
    masked = manager.get_public_config()["api_key"]

    # 前端把读到的掩码原样回写（很常见），真实密钥必须保持不变
    manager.update_config(api_key=masked, timeout=99)

    assert manager.get_config()["api_key"] == "sk-real-secret-key-1234"
    assert manager.get_config()["timeout"] == 99


def test_enabled_config_requires_base_url_key_and_model(manager):
    # 未启用时允许留空（用户可以填一半先存着）
    manager.update_config(enabled=False, api_key="")
    assert manager.is_ready()["ready"] is True

    with pytest.raises(ValueError):
        manager.update_config(enabled=True, base_url="", api_key="k-12345678", model_name="glm-ocr")


def test_is_ready_points_at_settings_page_when_enabled_but_incomplete(manager):
    # 「启用但缺字段」这个状态 update_config 的强校验是拦住的（见上一个用例），
    # 但手改 config/ocr.json、或环境变量只注入了一半时仍会出现，is_ready() 必须兜住。
    manager.path.write_text(
        '{"enabled": true, "base_url": "", "api_key": "", "model_name": ""}',
        encoding="utf-8",
    )
    status = manager.is_ready()

    assert status["ready"] is False
    assert "OCR 辅助" in status["reason"]


def test_endpoint_and_response_path_are_fixed_constants(manager):
    """端点与响应取值路径已经是常量，与配置内容无关。"""
    manager.update_config(protocol="whatever-from-an-old-file")
    assert manager.resolve_endpoint_path() == "/api/paas/v4/layout_parsing"
    assert manager.resolve_response_path() == "md_results"


def test_protocol_key_in_old_config_is_ignored_not_rejected(manager):
    """升级兼容：老配置文件里的 protocol 不该让保存失败。

    这些字段已经从产品里移除，但老用户的 `config/ocr.json` 里还留着它们。
    如果 `_validate` 还去校验，用户升级后会突然存不进配置。
    """
    manager.update_config(protocol="openai_chat", auth_scheme="", file_field="image")
    saved = manager.get_config()

    # 写回时不再落这些键
    assert "protocol" not in saved
    assert "auth_scheme" not in saved
    assert "file_field" not in saved


def test_removed_fields_do_not_survive_a_write(manager):
    """一次性确认 `CONFIG_FIELDS` 是配置的唯一真相。"""
    manager.update_config(protocol="layout_parsing", endpoint_path="/custom")
    manager.update_config(enabled=True, base_url="https://open.bigmodel.cn", api_key="k", model_name="glm-ocr")

    saved = manager.get_config()
    for gone in ("protocol", "endpoint_path", "response_path", "auth_scheme", "file_field", "prompt", "extra_params"):
        assert gone not in saved, f"{gone} 应该已经随协议抽象一起移除"
    for kept in ("enabled", "base_url", "api_key", "model_name", "timeout", "max_file_mb", "max_pages"):
        assert kept in saved, f"{kept} 仍然是可配字段"


# --------------------------------------------------------------------------- #
# 请求构造：智谱专用形状（字段名 / 鉴权头 / 端点路径都是常量）
# --------------------------------------------------------------------------- #

def test_layout_parsing_request_shape_is_zhipu_specific(image):
    """真机验证过的请求体形状。

    三件事必须同时成立，改任何一个都会让真机 400：
      * ``model`` 是 glm-ocr；
      * 文件放在 ``file`` 字段里，且是 data URI（不是 multipart）；
      * 两个体积巨大的可选项显式关掉，否则响应会带上几百 KB 的 base64。
    """
    payload = OcrClient(make_config())._build_layout_parsing_request(image)

    assert payload["model"] == "glm-ocr"
    assert payload["file"].startswith("data:image/png;base64,")
    assert payload["return_crop_images"] is False
    assert payload["need_layout_visualization"] is False


def test_layout_parsing_request_has_no_stray_config_fields(image):
    """请求体只由常量与 model 决定，不会被设置页的字段污染。"""
    payload = OcrClient(make_config())._build_layout_parsing_request(image)

    assert set(payload) == {"model", "file", "return_crop_images", "need_layout_visualization"}


def test_auth_header_is_always_bearer(image):
    """鉴权头固定 `Bearer <key>`（官方 OpenAPI 声明 security: bearerAuth）。"""
    client = OcrClient(make_config())
    assert client._headers()["Authorization"] == "Bearer sk-real-secret-key-1234"


def test_auth_header_uses_the_dotted_key_verbatim(image):
    """真机踩过的坑：key 是 `{id}.{secret}`，点之后那段绝不能丢。

    用户当时只复制到点之前，结果 401「令牌已过期或验证不正确」。
    这里锁住「整串原样拼进 Authorization」，避免将来有人画蛇添足去 split。
    """
    key = "0123456789abcdef0123456789abcdef.AbCd012345678901"
    client = OcrClient(make_config(api_key=key))
    assert client._headers()["Authorization"] == f"Bearer {key}"


def test_endpoint_url_is_base_plus_fixed_path(image):
    """端点 = base_url + 固定路径。base_url 仍可配（国内站/国际站/自建网关）。"""
    assert (
        OcrClient(make_config())._endpoint_url()
        == "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
    )
    assert (
        OcrClient(make_config(base_url="https://api.z.ai"))._endpoint_url()
        == "https://api.z.ai/api/paas/v4/layout_parsing"
    )


# --------------------------------------------------------------------------- #
# 体积上限：必须明确报错，不得静默压缩
# --------------------------------------------------------------------------- #

def test_oversize_file_raises_instead_of_silently_compressing(image):
    client = OcrClient(make_config(max_file_mb=0.0001))
    with pytest.raises(OcrError) as excinfo:
        client.recognize_image(image)

    assert "不做自动压缩" in str(excinfo.value)
    # 超限时不应该发出任何请求
    assert "512" in str(excinfo.value) or "0.0" in str(excinfo.value)


def test_missing_file_raises_ocr_error(tmp_path):
    client = OcrClient(make_config())
    with pytest.raises(OcrError):
        client.recognize_image(tmp_path / "nope.png")


# --------------------------------------------------------------------------- #
# 响应解析
# --------------------------------------------------------------------------- #

def test_parse_layout_parsing_reads_md_results_and_paged_blocks():
    body = {
        "md_results": "# 标题\n\n$E = mc^2$",
        "layout_details": [
            [
                {"index": 0, "label": "text", "content": "标题", "bbox_2d": [0.1, 0.2, 0.3, 0.4]},
                {"index": 1, "label": "formula", "content": "E = mc^2", "bbox_2d": [100, 200, 300, 400]},
            ]
        ],
    }
    result = OcrClient(make_config())._parse_layout_parsing(body)

    assert result.markdown == "# 标题\n\n$E = mc^2$"
    assert [block.label for block in result.blocks] == ["text", "formula"]
    assert result.protocol == "layout_parsing"
    # bbox_2d 上游对量纲自相矛盾，两种都归一化到 0-1
    assert result.blocks[0].bbox == [0.1, 0.2, 0.3, 0.4]
    assert result.blocks[1].bbox == [0.1, 0.2, 0.3, 0.4]


def test_result_protocol_is_pinned_to_layout_parsing():
    """`OcrResult.protocol` 保留但固定——产品里已经只剩这一条路。"""
    result = OcrClient(make_config())._parse_layout_parsing({"md_results": "x"})

    assert result.protocol == "layout_parsing"


def test_parse_layout_parsing_handles_real_shaped_response():
    """真机响应形状（2026-10-04 实测）：md_results 字符串 + layout_details 二维数组。

    `label == "image"` 的元素 content 恒为 null，解析时要变成空串而不是 "None"。
    """
    body = {
        "md_results": "一个物体以初速度 $ v_{0} $沿光滑斜面向上运动",
        "layout_details": [
            [
                {"index": 0, "label": "text", "content": "一个物体", "bbox_2d": [0.113, 0.164, 0.787, 0.539]},
                {"index": 1, "label": "image", "content": None, "bbox_2d": [1.0, 1.0, 1.0, 1.0]},
                {"index": 3, "label": "formula", "content": "S = V_{b} m", "bbox_2d": [1.0, 1.0, 1.0, 1.0]},
            ]
        ],
    }
    result = OcrClient(make_config())._parse_layout_parsing(body)

    assert result.markdown.startswith("一个物体")
    assert [b.label for b in result.blocks] == ["text", "image", "formula"]
    # image 元素的 content 是 None，必须落成空串——`str(None)` 会变成 "None" 混进正文
    assert result.blocks[1].content == ""
    assert result.blocks[1].bbox == [1.0, 1.0, 1.0, 1.0]


def test_layout_blocks_tolerate_flat_list_and_unknown_labels():
    body = {"layout_details": [{"index": 0, "label": "title", "content": "自建版才有的 label"}]}
    blocks = OcrClient._extract_layout_blocks(body)

    assert len(blocks) == 1
    assert blocks[0].content == "自建版才有的 label"


def test_result_text_falls_back_to_blocks():
    from app.services.ocr_client import OcrResult

    result = OcrResult(markdown="", blocks=[OcrBlock(label="text", content="只有块")])
    assert result.text == "只有块"


# --------------------------------------------------------------------------- #
# 错误解析与工具函数
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "payload",
    [
        {"error": {"code": "1210", "message": "Invalid API parameter"}},
        {"code": "1210", "message": "Invalid API parameter", "status": 400},
    ],
)
def test_extract_error_handles_both_envelopes(payload):
    code, message = _extract_error(payload, "")
    assert code == "1210"
    assert message == "Invalid API parameter"


def test_extract_error_falls_back_to_raw_body():
    code, message = _extract_error("not a dict", "upstream html")
    assert code is None
    assert "upstream html" in message


def test_dig_supports_index_segments():
    payload = {"choices": [{"message": {"content": "ok"}}]}
    assert _dig(payload, "choices.0.message.content") == "ok"
    assert _dig(payload, "choices.9.message.content") is None


def test_normalize_bbox_clamps_out_of_range():
    assert _normalize_bbox([-1, 0.5, 2, 0.7]) == [0.0, 0.5, 1.0, 0.7]
    assert _normalize_bbox("nonsense") is None


def test_http_error_carries_upstream_text():
    client = OcrClient(make_config())
    error = client._http_error(400, '{"code":"1210","message":"Invalid API parameter"}')

    assert error.status_code == 400
    assert error.code == "1210"
    assert "Invalid API parameter" in error.detail


# --------------------------------------------------------------------------- #
# 可重试性判定：配错 key 不该白跑三次重试
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "status,code",
    [
        (401, "401"),   # 真机遇到的那个：key 不对
        (403, None),    # 权限不足
        (413, None),    # 体积超限
        (400, "1000"),  # 鉴权失败
        (400, "1003"),  # Token 已过期
        (400, "1113"),  # 余额不足
        (400, "1211"),  # 模型不存在
    ],
)
def test_auth_and_config_errors_are_not_retryable(status, code):
    """这些错误重试一次结果完全一样——只有改了配置才可能成功。

    真机日志：同一个 401 重试 3 次，每次都重跑一遍 LLM 总结（43s→72s→111s），
    最后失败得一模一样。重试在这里是纯浪费。
    """
    client = OcrClient(make_config())
    error = client._http_error(status, '{"error":{"code":"%s","message":"x"}}' % (code or status))

    assert error.non_retryable is True


@pytest.mark.parametrize(
    "status",
    [
        500,  # 上游内部错误，可能自愈
        502,  # 网关抖动
        504,  # 超时
        429,  # 限流：等一会儿再试是有意义的
    ],
)
def test_transient_errors_stay_retryable(status):
    """网络抖动与 5xx 必须保持可重试，不能把「等一会儿就好」也判死。"""
    client = OcrClient(make_config())
    error = client._http_error(status, '{"error":{"code":"500","message":"boom"}}')

    assert error.non_retryable is False


def test_network_failure_has_no_non_retryable_flag():
    """构造失败（连接错误）不带标记：它连 HTTP 状态码都没有。"""
    error = OcrError("OCR 请求失败：连接被重置")

    assert error.non_retryable is False


def test_non_retryable_flag_reaches_the_generator_via_getattr():
    """确认 note.generate 顶层 except 读得这个属性（机制对接，不是重复实现）。

    `note.py` 用 `bool(getattr(exc, "non_retryable", False))` 取它，
    所以属性名一旦改动，重试策略会静默退回「什么都重试」。
    """
    client = OcrClient(make_config())
    error = client._http_error(401, '{"error":{"code":"401","message":"令牌已过期或验证不正确"}}')

    assert bool(getattr(error, "non_retryable", False)) is True


# --------------------------------------------------------------------------- #
# 配置路径解析：不得依赖进程 CWD
# --------------------------------------------------------------------------- #

def test_default_config_path_is_absolute_and_cwd_independent():
    """默认路径必须解析成绝对路径，否则换个工作目录就读成空配置。

    原实现是 `Path("config/ocr.json")`：uvicorn 从 backend/ 启动时正常，
    但从仓库根跑脚本就静默拿到空配置，报错还指向「未配置 OCR 服务地址」。
    """
    manager = OcrConfigManager()

    assert manager.path.is_absolute()
    assert manager.path.name == "ocr.json"
    assert manager.path.parent.name == "config"


def test_default_config_path_points_into_backend():
    """解析基准是 backend/，不是进程 CWD。"""
    manager = OcrConfigManager()

    # backend/config/ocr.json —— 上溯两级（config → backend）
    assert manager.path.parent.parent.name == "backend"


def test_explicit_absolute_path_is_untouched(tmp_path):
    """显式传入的绝对路径原样使用，不能被改写到 backend/ 下面去。"""
    target = tmp_path / "custom-ocr.json"
    manager = OcrConfigManager(str(target))

    assert manager.path == target


# --------------------------------------------------------------------------- #
# 连接测试：永不抛异常，失败也要把原始错误交出去
# --------------------------------------------------------------------------- #

def test_connection_failure_returns_raw_error_instead_of_raising(tmp_path):
    # FakeSession 是鸭子类型替身，故意不是 requests.Session 的子类
    session: Any = FakeSession(error=requests.ConnectionError("名字解析失败"))
    client = OcrClient(make_config(), session=session)
    result = client.test_connection()

    assert result["ok"] is False
    assert "名字解析失败" in str(result.get("detail") or result.get("message"))


def test_connection_success_reports_protocol_and_model():
    session: Any = FakeSession(response=FakeResponse({"md_results": "OCR TEST 12345"}))
    client = OcrClient(make_config(), session=session)
    result = client.test_connection()

    assert result["ok"] is True
    assert result["protocol"] == "layout_parsing"
    assert result["model_name"] == "glm-ocr"
    # 测试图是现画的，请求必须真的发出去过一次
    assert len(session.calls) == 1
    assert session.calls[0]["json"]["model"] == "glm-ocr"


def test_connection_reports_upstream_error_body():
    session: Any = FakeSession(
        response=FakeResponse({"error": {"code": "1001", "message": "鉴权失败"}}, status_code=401)
    )
    result = OcrClient(make_config(), session=session).test_connection()

    assert result["ok"] is False
    assert "鉴权失败" in str(result.get("message") or result.get("detail"))


# --------------------------------------------------------------------------- #
# 路由注册
# --------------------------------------------------------------------------- #

def test_ocr_router_is_registered():
    from app.routers import ocr

    paths = {getattr(route, "path", "") for route in ocr.router.routes}
    assert {"/ocr_config", "/ocr_config/test"} <= paths
    # 协议下拉框随协议抽象一起移除，端点不应该再存在
    assert "/ocr_config/protocols" not in paths
