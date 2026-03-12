from __future__ import annotations

import hashlib
from typing import Iterable

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.services.observability.domain_events import record_domain_event
from app.services.rate_limiter import RateLimitDecision, get_rate_limit_policy, rate_limiter


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def hash_key_part(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_identity_key(parts: Iterable[str]) -> str:
    normalized = [part.strip() for part in parts if part and part.strip()]
    return "|".join(normalized) if normalized else "unknown"


def _raise_rate_limited(decision: RateLimitDecision, *, message: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "rate_limited",
            "message": message,
            "details": {
                "retry_after_seconds": decision.retry_after_seconds,
            },
        },
        headers={"Retry-After": str(decision.retry_after_seconds)},
    )


def enforce_rate_limit(
    *,
    request: Request,
    db: Session,
    policy_name: str,
    identity_key: str,
    message: str = "Too many requests. Please retry later.",
    actor_type: str = "system",
    actor_id: int | None = None,
    organization_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    related_payment_id: int | None = None,
    related_appointment_id: int | None = None,
    related_payout_id: int | None = None,
) -> None:
    policy = get_rate_limit_policy(policy_name)
    decision = rate_limiter.check(policy=policy, key=identity_key)
    if decision.allowed:
        return

    record_domain_event(
        db,
        event_type="rate_limit_exceeded",
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        related_payment_id=related_payment_id,
        related_appointment_id=related_appointment_id,
        related_payout_id=related_payout_id,
        status="failure",
        payload={
            "policy": decision.policy_name,
            "limit": decision.limit,
            "retry_after_seconds": decision.retry_after_seconds,
            "path": request.url.path,
            "method": request.method,
            "backend": decision.backend,
            "key_fingerprint": decision.key_fingerprint,
        },
    )
    _raise_rate_limited(decision, message=message)
