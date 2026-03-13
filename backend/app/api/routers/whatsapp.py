from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.observability.domain_events import record_domain_event
from app.services.observability.metrics import increment_counter
from app.services.whatsapp import WhatsAppService, normalize_whatsapp_messages

router = APIRouter()


def _validate_signature(*, body: bytes, provided_signature: str | None) -> bool:
    app_secret = (settings.whatsapp_app_secret or "").strip()
    if not app_secret:
        return True
    if provided_signature is None:
        return False
    normalized_signature = provided_signature.strip()
    expected = hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(normalized_signature, f"sha256={expected}")


@router.get("/webhook")
def verify_whatsapp_webhook(request: Request) -> PlainTextResponse:
    mode = request.query_params.get("hub.mode")
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    expected_token = (settings.whatsapp_verify_token or "").strip()
    if not expected_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook verify token is not configured")

    if mode == "subscribe" and verify_token == expected_token and challenge:
        return PlainTextResponse(content=challenge, status_code=status.HTTP_200_OK)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed")


@router.post("/webhook")
async def receive_whatsapp_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, int | str]:
    raw_body = await request.body()
    if not _validate_signature(body=raw_body, provided_signature=x_hub_signature_256):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload")

    increment_counter("whatsapp_webhook_received_total")
    normalized_messages = normalize_whatsapp_messages(payload)

    result = WhatsAppService(db).process_messages(normalized_messages)
    record_domain_event(
        db,
        event_type="whatsapp_webhook_received",
        actor_type="system",
        status="success",
        payload={
            "message_count": len(normalized_messages),
            "processed_messages": result.processed_messages,
            "duplicate_messages": result.duplicate_messages,
            "outbound_sent": result.outbound_sent,
            "outbound_failed": result.outbound_failed,
        },
    )

    return {
        "status": "accepted",
        "processed_messages": result.processed_messages,
        "duplicate_messages": result.duplicate_messages,
        "outbound_sent": result.outbound_sent,
        "outbound_failed": result.outbound_failed,
    }
