from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from time import sleep
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schemas.whatsapp import (
    WhatsAppButtonOption,
    WhatsAppGatewaySendResult,
    WhatsAppListSection,
)

logger = logging.getLogger(__name__)


class WhatsAppGatewayError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_payload = response_payload or {}


@dataclass(frozen=True)
class WhatsAppGatewayConfig:
    base_url: str
    api_version: str
    phone_number_id: str
    access_token: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float


class WhatsAppCloudApiGateway:
    def __init__(self) -> None:
        self.config = WhatsAppGatewayConfig(
            base_url=settings.whatsapp_cloud_api_base_url.rstrip("/"),
            api_version=settings.whatsapp_cloud_api_version.strip(),
            phone_number_id=(settings.whatsapp_phone_number_id or "").strip(),
            access_token=(settings.whatsapp_access_token or "").strip(),
            timeout_seconds=float(settings.whatsapp_outbound_timeout_seconds),
            max_retries=max(0, int(settings.whatsapp_outbound_max_retries)),
            retry_backoff_seconds=max(0.0, float(settings.whatsapp_outbound_retry_backoff_seconds)),
        )

    def send_text(self, *, to: str, body: str) -> WhatsAppGatewaySendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body,
            },
        }
        return self._post_messages(payload)

    def send_buttons(
        self,
        *,
        to: str,
        body: str,
        buttons: list[WhatsAppButtonOption],
    ) -> WhatsAppGatewaySendResult:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": option.id, "title": option.title}}
                        for option in buttons
                    ]
                },
            },
        }
        return self._post_messages(payload)

    def send_list(
        self,
        *,
        to: str,
        body: str,
        list_button_text: str,
        sections: list[WhatsAppListSection],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> WhatsAppGatewaySendResult:
        interactive_payload: dict[str, Any] = {
            "type": "list",
            "body": {"text": body},
            "action": {
                "button": list_button_text,
                "sections": [
                    {
                        "title": section.title,
                        "rows": [
                            {
                                "id": row.id,
                                "title": row.title,
                                "description": row.description,
                            }
                            for row in section.rows
                        ],
                    }
                    for section in sections
                ],
            },
        }
        if header_text:
            interactive_payload["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive_payload["footer"] = {"text": footer_text}

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": interactive_payload,
        }
        return self._post_messages(payload)

    def _post_messages(self, payload: dict[str, Any]) -> WhatsAppGatewaySendResult:
        if not self.config.phone_number_id or not self.config.access_token:
            raise WhatsAppGatewayError("WhatsApp Cloud API credentials are not configured.")

        endpoint = (
            f"{self.config.base_url}/{self.config.api_version}/"
            f"{self.config.phone_number_id}/messages"
        )
        response_payload = self._post_with_retries(endpoint=endpoint, payload=payload)
        external_message_id = None
        messages = response_payload.get("messages")
        if isinstance(messages, list) and messages:
            first = messages[0]
            if isinstance(first, dict):
                message_id = first.get("id")
                if isinstance(message_id, str) and message_id.strip():
                    external_message_id = message_id.strip()
        return WhatsAppGatewaySendResult(
            external_message_id=external_message_id,
            provider_payload=response_payload,
        )

    def _post_with_retries(self, *, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.access_token}",
            "Content-Type": "application/json",
        }
        attempts = self.config.max_retries + 1

        last_error: WhatsAppGatewayError | None = None
        for attempt in range(attempts):
            request = Request(endpoint, data=request_bytes, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    response_body = response.read().decode("utf-8")
                if not response_body:
                    return {}
                parsed = json.loads(response_body)
                if isinstance(parsed, dict):
                    return parsed
                raise WhatsAppGatewayError("WhatsApp Cloud API returned a non-object response.")
            except HTTPError as exc:
                payload_obj = self._safe_json_from_bytes(exc.read())
                is_retryable = exc.code >= 500
                last_error = WhatsAppGatewayError(
                    f"WhatsApp Cloud API request failed with status {exc.code}.",
                    status_code=exc.code,
                    response_payload=payload_obj,
                )
                logger.warning(
                    "whatsapp_gateway_http_error status_code=%s retryable=%s attempt=%s/%s",
                    exc.code,
                    is_retryable,
                    attempt + 1,
                    attempts,
                )
                if not is_retryable or attempt >= attempts - 1:
                    raise last_error
            except URLError as exc:
                last_error = WhatsAppGatewayError(f"WhatsApp Cloud API network error: {exc.reason}")
                logger.warning(
                    "whatsapp_gateway_network_error attempt=%s/%s reason=%s",
                    attempt + 1,
                    attempts,
                    exc.reason,
                )
                if attempt >= attempts - 1:
                    raise last_error
            if self.config.retry_backoff_seconds > 0:
                sleep(self.config.retry_backoff_seconds * (2**attempt))

        if last_error is not None:
            raise last_error
        raise WhatsAppGatewayError("WhatsApp Cloud API request failed.")

    @staticmethod
    def _safe_json_from_bytes(body: bytes) -> dict[str, Any]:
        if not body:
            return {}
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return {"raw_body": body.decode("utf-8", errors="replace")}
        return payload if isinstance(payload, dict) else {"payload": payload}
