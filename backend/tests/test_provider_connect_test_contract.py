from unittest.mock import patch

import pytest

from app.routers.provider import TestRequest as ConnectTestRequest, gpt_connect_test


def test_request_accepts_provider_id_shape():
    request = ConnectTestRequest(provider_id="provider-1")
    assert request.provider_identifier == "provider-1"
    assert request.model is None


def test_request_preserves_legacy_id_and_model_shape():
    request = ConnectTestRequest(id="provider-1", model="model-a")
    assert request.provider_identifier == "provider-1"
    assert request.model == "model-a"


def test_request_rejects_missing_or_conflicting_identifiers():
    with pytest.raises(ValueError, match="either id or provider_id is required"):
        ConnectTestRequest()
    with pytest.raises(ValueError, match="must match"):
        ConnectTestRequest(id="provider-1", provider_id="provider-2")


@pytest.mark.parametrize(
    ("payload", "expected_id", "expected_model"),
    [
        ({"provider_id": "provider-1"}, "provider-1", None),
        ({"id": "provider-1", "model": "model-a"}, "provider-1", "model-a"),
    ],
)
def test_route_normalizes_both_payload_shapes(payload, expected_id, expected_model):
    with patch("app.routers.provider.ModelService.connect_test", return_value=True) as connect_test:
        response = gpt_connect_test(ConnectTestRequest(**payload))

    assert response.status_code == 200
    connect_test.assert_called_once_with(expected_id, model=expected_model)
