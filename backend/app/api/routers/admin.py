from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.health import build_readiness_payload
from app.db.session import get_db
from app.dependencies.rate_limit import build_identity_key, enforce_rate_limit
from app.dependencies.auth import get_current_active_user, require_org_membership, require_platform_admin
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.domain_event_repository import DomainEventRepository
from app.models.organization import Organization
from app.schemas.admin import AdminPing, DomainEventRead, SystemReadinessSummary
from app.services.operations.migration_status import get_migration_status

REMINDER_TASK_NAME = "bookpoint.notifications.appointment_reminder"
PAYMENT_EXPIRATION_TASK_NAME = "bookpoint.payments.expire_pending"
PAYOUT_PROCESSING_TASK_NAME = "bookpoint.payouts.process_pending"
OPS_CLEANUP_TASK_NAME = "bookpoint.ops.cleanup_operational_data"


def _require_admin_internal_endpoints_enabled() -> None:
    if not settings.enable_admin_internal_endpoints:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


router = APIRouter(dependencies=[Depends(_require_admin_internal_endpoints_enabled)])


@router.get("/ping", response_model=AdminPing)
def admin_ping(_: User = Depends(require_platform_admin)) -> AdminPing:
    return AdminPing(status="admin_ok")


@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_platform_admin),
) -> dict[str, int]:
    organizations_count = db.scalar(select(func.count(Organization.id))) or 0
    return {"organizations_count": organizations_count}


@router.get("/system/readiness-summary", response_model=SystemReadinessSummary)
def get_system_readiness_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_platform_admin),
) -> SystemReadinessSummary:
    _, dependency_payload = build_readiness_payload()
    checks = dependency_payload.get("checks", {})
    database_ok = bool(isinstance(checks, dict) and checks.get("database", {}).get("status") == "ok")
    redis_ok = bool(isinstance(checks, dict) and checks.get("redis", {}).get("status") == "ok")

    migration_status = get_migration_status(db)
    warnings: list[str] = []
    if settings.enable_docs and settings.is_production:
        warnings.append("ENABLE_DOCS is true in production.")
    if not settings.enable_rate_limiting:
        warnings.append("ENABLE_RATE_LIMITING is disabled.")
    if not database_ok:
        warnings.append("Database dependency check is failing.")
    if not redis_ok:
        warnings.append("Redis dependency check is failing.")
    if not bool(migration_status.get("up_to_date")):
        warnings.append("Database migration revision is not at head.")

    return SystemReadinessSummary.model_validate(
        {
            "environment": settings.resolved_environment,
            "docs_enabled": settings.enable_docs,
            "metrics_enabled": settings.enable_metrics,
            "admin_internal_endpoints_enabled": settings.enable_admin_internal_endpoints,
            "rate_limiting_enabled": settings.enable_rate_limiting,
            "database_reachable": database_ok,
            "redis_reachable": redis_ok,
            "dependencies": checks if isinstance(checks, dict) else {},
            "migrations": migration_status,
            "cleanup_jobs": {
                "task_name": OPS_CLEANUP_TASK_NAME,
                "interval_seconds": settings.ops_cleanup_interval_seconds,
                "retention_days": {
                    "domain_events": settings.domain_events_retention_days,
                    "idempotency_keys": settings.idempotency_keys_retention_days,
                },
                "related_periodic_tasks": {
                    "reminder_scheduler": REMINDER_TASK_NAME,
                    "payment_expiration": PAYMENT_EXPIRATION_TASK_NAME,
                    "payout_processing": PAYOUT_PROCESSING_TASK_NAME,
                },
            },
            "warnings": warnings,
        }
    )


def _require_event_visibility_access(
    *,
    db: Session,
    user: User,
    organization_id: int | None,
) -> None:
    if user.is_platform_admin:
        return
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="organization_id is required for non-platform admins.",
        )
    require_org_membership(
        db,
        organization_id=organization_id,
        user=user,
        allowed_roles=(MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.STAFF),
    )


@router.get("/events", response_model=list[DomainEventRead])
def list_domain_events(
    request: Request,
    event_type: str | None = Query(default=None),
    organization_id: int | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[DomainEventRead]:
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="admin_events",
        identity_key=build_identity_key([f"user:{current_user.id}"]),
        actor_type="user",
        actor_id=current_user.id,
    )
    _require_event_visibility_access(db=db, user=current_user, organization_id=organization_id)
    events = DomainEventRepository(db).list_events(
        event_type=event_type,
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status_value,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    if not current_user.is_platform_admin:
        events = [event for event in events if event.organization_id == organization_id]
    return [DomainEventRead.model_validate(event) for event in events]


@router.get("/events/{event_id}", response_model=DomainEventRead)
def get_domain_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DomainEventRead:
    event = DomainEventRepository(db).get(event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain event not found")
    if not current_user.is_platform_admin:
        if event.organization_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization access denied")
        require_org_membership(
            db,
            organization_id=event.organization_id,
            user=current_user,
            allowed_roles=(MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.STAFF),
        )
    return DomainEventRead.model_validate(event)
