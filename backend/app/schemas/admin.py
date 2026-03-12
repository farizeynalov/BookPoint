from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class AdminPing(ORMModel):
    status: str


class DomainEventRead(ORMModel):
    id: int
    event_type: str
    entity_type: str | None = None
    entity_id: int | None = None
    organization_id: int | None = None
    actor_type: str
    actor_id: int | None = None
    request_id: str | None = None
    related_payment_id: int | None = None
    related_appointment_id: int | None = None
    related_payout_id: int | None = None
    status: str
    payload_json: dict[str, Any] | None = None
    created_at: datetime


class SystemReadinessSummary(ORMModel):
    environment: str
    docs_enabled: bool
    metrics_enabled: bool
    admin_internal_endpoints_enabled: bool
    rate_limiting_enabled: bool
    database_reachable: bool
    redis_reachable: bool
    dependencies: dict[str, dict[str, Any]]
    migrations: dict[str, Any]
    cleanup_jobs: dict[str, Any]
    warnings: list[str]
