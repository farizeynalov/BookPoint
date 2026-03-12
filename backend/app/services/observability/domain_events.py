from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.request_context import get_request_id
from app.models.domain_event import DomainEvent
from app.repositories.domain_event_repository import DomainEventRepository

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {
    "token",
    "secret",
    "password",
    "authorization",
    "access_token",
    "refresh_token",
    "webhook_secret",
}


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = _sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value[:100]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record_domain_event(
    db: Session,
    *,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    organization_id: int | None = None,
    actor_type: str = "system",
    actor_id: int | None = None,
    request_id: str | None = None,
    related_payment_id: int | None = None,
    related_appointment_id: int | None = None,
    related_payout_id: int | None = None,
    status: str = "info",
    payload: dict[str, Any] | None = None,
    auto_commit: bool = True,
) -> DomainEvent | None:
    resolved_request_id = request_id or get_request_id()
    sanitized_payload = _sanitize_payload(payload or {})
    try:
        return DomainEventRepository(db).create(
            auto_commit=auto_commit,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            request_id=resolved_request_id,
            related_payment_id=related_payment_id,
            related_appointment_id=related_appointment_id,
            related_payout_id=related_payout_id,
            status=status,
            payload_json=sanitized_payload,
        )
    except Exception:
        if auto_commit:
            db.rollback()
        logger.exception(
            "domain_event_persist_failed event_type=%s entity_type=%s entity_id=%s",
            event_type,
            entity_type,
            entity_id,
        )
        return None
