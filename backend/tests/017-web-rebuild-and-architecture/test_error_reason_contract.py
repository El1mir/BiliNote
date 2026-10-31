"""spec 017 ticket 005：后端错误必须带结构化 reason。

背景：onboarding 曾经靠 ``"已存在" in error_msg`` 判断「供应商重名」。这有两个问题：

1. 判定依赖中文文案 —— 后端改一个字，判定就静默失效；
2. 英文界面里被迫保留一个「不许翻译」的 i18n 键（``onboarding.error.existsMarker``），
   而且模型重名的分支实际上永远匹配不上：``POST /models`` 无论重名还是其它失败都只回
   「模型添加失败」，于是「模型已存在」会让整个引导步骤失败。

这些用例把契约钉在 ``data.reason`` 上。
"""

import json

import pytest
from app.exceptions.provider import ProviderNameExistsError


def _body(response):
    return json.loads(response.body.decode("utf-8"))


def test_provider_service_raises_name_exists_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重名必须抛专用异常，而不是一个裸 ValueError。"""
    from app.services import provider as provider_service

    monkeypatch.setattr(
        provider_service,
        "get_provider_by_name",
        lambda name: {"id": "existing", "name": name},
    )

    with pytest.raises(ProviderNameExistsError) as caught:
        provider_service.ProviderService.add_provider(
            name="OpenAI",
            api_key="sk-x",
            base_url="https://example.test",
            logo="custom",
            type_="custom",
        )

    # 仍然是一个 ValueError：既有调用方的捕获语义不变。
    assert isinstance(caught.value, ValueError)


def test_add_provider_route_returns_structured_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重名时路由要回 400 + data.reason，前端才不必匹配中文文案。"""
    from app.routers import provider as provider_router

    def _boom(**kwargs):
        raise ProviderNameExistsError("供应商名称已存在: OpenAI")

    monkeypatch.setattr(provider_router.ProviderService, "add_provider", _boom)

    response = provider_router.add_provider(
        provider_router.ProviderRequest(
            name="OpenAI",
            api_key="sk-x",
            base_url="https://example.test",
            type="custom",
        )
    )
    body = _body(response)

    assert body["code"] == 400
    assert body["data"] == {"reason": "provider_name_exists"}


def test_create_model_outcome_reports_existing_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型重名要能被区分出来，而不是笼统的「添加失败」。"""
    from app.services import model as model_service

    monkeypatch.setattr(
        model_service.ProviderService, "get_provider_by_id", lambda pid: {"id": pid}
    )
    monkeypatch.setattr(
        model_service,
        "get_model_by_provider_and_name",
        lambda pid, name: {"id": 1, "provider_id": pid, "model_name": name},
    )

    assert model_service.ModelService.create_model_outcome("p1", "gpt-4o") == "exists"


def test_create_model_outcome_creates_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import model as model_service

    inserted: list[tuple] = []
    monkeypatch.setattr(
        model_service.ProviderService, "get_provider_by_id", lambda pid: {"id": pid}
    )
    monkeypatch.setattr(
        model_service, "get_model_by_provider_and_name", lambda pid, name: None
    )
    monkeypatch.setattr(
        model_service,
        "insert_model",
        lambda provider_id, model_name: inserted.append((provider_id, model_name)),
    )

    assert model_service.ModelService.create_model_outcome("p1", "gpt-4o") == "created"
    assert inserted == [("p1", "gpt-4o")]
    # 布尔入口保持兼容：它把 outcome 压成 bool，既有调用方无需改动。
    assert model_service.ModelService.add_new_model("p1", "gpt-4o") is True


def test_create_model_outcome_reports_missing_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import model as model_service

    monkeypatch.setattr(
        model_service.ProviderService, "get_provider_by_id", lambda pid: None
    )

    assert (
        model_service.ModelService.create_model_outcome("p1", "gpt-4o")
        == "provider_missing"
    )


def test_create_model_route_returns_structured_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers import model as model_router

    monkeypatch.setattr(
        model_router.ModelService,
        "create_model_outcome",
        staticmethod(lambda pid, name: "exists"),
    )

    response = model_router.create_model(
        model_router.CreateModelRequest(provider_id="p1", model_name="gpt-4o")
    )
    body = _body(response)

    assert body["code"] == 400
    assert body["data"] == {"reason": "model_name_exists"}
