"""OCR 辅助模式的设置接口（spec 008 ticket 01 §1 / §3）。

只做三件事：读配置、写配置、连接测试。**不参与生成流程**——
生成流程怎么用 OCR 是 ticket 02 的事。

连接测试为什么必须有
--------------------
上游文档在多处自相矛盾（鉴权头是否带 ``Bearer``、``bbox_2d`` 量纲、页数上限），
靠读文档无法确定哪个组合真的能通。所以设置页给一个「连接测试」按钮，
用一张现画的测试图打一次真实调用，把**上游原始错误原文**原样回给用户。
真机验证（2026-10-04）确认了鉴权与响应形状之后，那些争议字段已固化为常量，
但「连接测试」仍然有价值：它能第一时间告诉用户 key 是不是抄漏了
（最常见的失败就是把 ``{id}.{secret}`` 只复制到点之前）。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ocr_client import build_ocr_client
from app.services.ocr_config_manager import OcrConfigManager
from app.utils.logger import get_logger
from app.utils.response import ResponseWrapper as R

logger = get_logger(__name__)

router = APIRouter()

# 与 TranscriberConfigManager 同一套路：模块级单例，配置落在 config/ocr.json
ocr_config_manager = OcrConfigManager()


class OcrConfigRequest(BaseModel):
    """所有字段都可选：只提交改动过的字段即可。

    ``api_key`` 允许提交打码值（含 ``*``），服务端会识别并丢弃，
    避免前端把掩码回写覆盖真实密钥。

    已收敛为智谱专用：端点路径、鉴权头形态、文件字段名、响应取值路径
    都固化在 `ocr_config_manager` 的模块常量里，不再是请求字段。
    """

    enabled: Optional[bool] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    timeout: Optional[int] = None
    max_file_mb: Optional[float] = None
    max_pages: Optional[int] = None


@router.get("/ocr_config")
def get_ocr_config():
    """读取 OCR 配置（``api_key`` 已打码，并附带 ``_defaults`` 供前端做占位提示）。"""
    return R.success(ocr_config_manager.get_public_config())


@router.post("/ocr_config")
def update_ocr_config(data: OcrConfigRequest):
    """保存 OCR 配置。

    只在**启用**时做强校验（缺 ``base_url``/``api_key``/``model_name`` 会报错），
    未启用时允许留空，用户可以先填一半再回来补。
    """
    try:
        ocr_config_manager.update_config(**data.model_dump(exclude_none=True))
    except ValueError as exc:
        return R.error(msg=str(exc), code=400)
    except Exception as exc:  # 写盘失败等
        logger.exception("保存 OCR 配置失败")
        return R.error(msg=f"保存 OCR 配置失败：{exc}", code=500)

    return R.success(ocr_config_manager.get_public_config(), msg="配置已保存")


@router.post("/ocr_config/test")
def test_ocr_config(data: Optional[OcrConfigRequest] = None):
    """连接测试：用内置测试图打一次真实调用。

    可以带一个**未保存的草稿**覆盖当前配置来做测试——否则用户必须先把可能错误的
    密钥存盘才能点测试，体验很差。草稿只用于本次调用，不落盘。
    """
    saved = ocr_config_manager.get_config_with_env_fallback()

    if data is not None:
        draft = data.model_dump(exclude_none=True)
        for key, value in draft.items():
            # 打码值视为「未改动」，沿用已保存的真实密钥
            if key == "api_key" and "*" in str(value):
                continue
            saved[key] = value

    client = build_ocr_client(ocr_config_manager)
    # 用草稿覆盖客户端的配置视图（不写回 manager）
    client._config = saved  # noqa: SLF001 - 有意为之：草稿只作用于本次调用

    result = client.test_connection()
    if result.get("ok"):
        return R.success(result, msg="连接成功")
    return R.error(msg=result.get("message") or "连接失败", code=400, data=result)
