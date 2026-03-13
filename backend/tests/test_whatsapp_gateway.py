from __future__ import annotations

import io
import json
from urllib.error import HTTPError, URLError

import pytest

from app.schemas.whatsapp import WhatsAppButtonOption, WhatsAppListRow, WhatsAppListSection
from app.services.whatsapp.gateway import WhatsAppCloudApiGateway, WhatsAppGatewayError


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _set_gateway_config(monkeypatch) -> None:
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_access_token", "wa-access-token")
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_phone_number_id", "100200300")
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_cloud_api_base_url", "https://graph.facebook.com")
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_cloud_api_version", "v21.0")
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_outbound_timeout_seconds", 1.0)
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_outbound_retry_backoff_seconds", 0.0)


def test_whatsapp_gateway_retries_and_succeeds_on_transient_http_error(monkeypatch) -> None:
    _set_gateway_config(monkeypatch)
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_outbound_max_retries", 1)
    call_count = {"value": 0}

    def _urlopen(_request, timeout):  # noqa: ARG001
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise HTTPError(
                url="https://graph.facebook.com/v21.0/100200300/messages",
                code=500,
                msg="server error",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"message":"temporary"}}'),
            )
        return _FakeHTTPResponse({"messages": [{"id": "wamid.success"}]})

    monkeypatch.setattr("app.services.whatsapp.gateway.urlopen", _urlopen)
    gateway = WhatsAppCloudApiGateway()
    result = gateway.send_buttons(
        to="15550090001",
        body="Choose one",
        buttons=[WhatsAppButtonOption(id="menu:book", title="Book")],
    )
    assert result.external_message_id == "wamid.success"
    assert call_count["value"] == 2


def test_whatsapp_gateway_raises_error_on_network_failure(monkeypatch) -> None:
    _set_gateway_config(monkeypatch)
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_outbound_max_retries", 0)
    def _urlopen(_request, timeout):  # noqa: ARG001
        raise URLError("boom")

    monkeypatch.setattr("app.services.whatsapp.gateway.urlopen", _urlopen)
    gateway = WhatsAppCloudApiGateway()
    with pytest.raises(WhatsAppGatewayError, match="network error"):
        gateway.send_text(to="15550090002", body="Hello")


def test_whatsapp_gateway_sends_list_payload(monkeypatch) -> None:
    _set_gateway_config(monkeypatch)
    monkeypatch.setattr("app.services.whatsapp.gateway.settings.whatsapp_outbound_max_retries", 0)

    captured_payload: dict = {}

    def _urlopen(request, timeout):  # noqa: ARG001
        captured_payload.update(json.loads(request.data.decode("utf-8")))
        return _FakeHTTPResponse({"messages": [{"id": "wamid.list"}]})

    monkeypatch.setattr("app.services.whatsapp.gateway.urlopen", _urlopen)
    gateway = WhatsAppCloudApiGateway()
    result = gateway.send_list(
        to="15550090003",
        body="Select slot",
        list_button_text="Slots",
        sections=[
            WhatsAppListSection(
                title="Today",
                rows=[WhatsAppListRow(id="slot:1", title="09:00 UTC", description="Morning")],
            )
        ],
    )
    assert result.external_message_id == "wamid.list"
    assert captured_payload["type"] == "interactive"
    assert captured_payload["interactive"]["type"] == "list"
