from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routers import admin as admin_router_module
from app.core.config import Settings, settings
from app.main import create_app
from app.models.domain_event import DomainEvent
from app.models.idempotency_key import IdempotencyKey
from app.models.user import User
from app.services.operations import migration_status as migration_status_module
from app.workers import tasks as worker_tasks


def _promote_to_platform_admin(db_session: Session, user_id: int) -> None:
    user = db_session.get(User, user_id)
    assert user is not None
    user.is_platform_admin = True
    db_session.add(user)
    db_session.commit()


def test_docs_can_be_disabled_by_config() -> None:
    app = create_app(Settings(_env_file=None, enable_docs=False))
    with TestClient(app) as docs_client:
        docs_response = docs_client.get("/docs")
        openapi_response = docs_client.get("/openapi.json")
        assert docs_response.status_code == 404
        assert openapi_response.status_code == 404


def test_readiness_summary_endpoint_is_protected(client: TestClient) -> None:
    response = client.get("/api/v1/admin/system/readiness-summary")
    assert response.status_code == 401


def test_readiness_summary_returns_expected_config_flags(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_user: User,
    db_session: Session,
    monkeypatch,
) -> None:
    _promote_to_platform_admin(db_session, seeded_user.id)

    monkeypatch.setattr(
        admin_router_module,
        "build_readiness_payload",
        lambda: (
            True,
            {
                "status": "ok",
                "checks": {
                    "database": {"status": "ok", "latency_ms": 1.2},
                    "redis": {"status": "ok", "latency_ms": 1.1},
                },
            },
        ),
    )
    monkeypatch.setattr(
        admin_router_module,
        "get_migration_status",
        lambda db: {
            "status": "up_to_date",
            "up_to_date": True,
            "head_revisions": ["head-1"],
            "current_revisions": ["head-1"],
            "pending_revisions": [],
            "error": None,
        },
    )

    response = client.get("/api/v1/admin/system/readiness-summary", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["environment"] == settings.resolved_environment
    assert payload["docs_enabled"] == settings.enable_docs
    assert payload["metrics_enabled"] == settings.enable_metrics
    assert payload["admin_internal_endpoints_enabled"] == settings.enable_admin_internal_endpoints
    assert payload["rate_limiting_enabled"] == settings.enable_rate_limiting
    assert payload["database_reachable"] is True
    assert payload["redis_reachable"] is True
    assert payload["migrations"]["status"] == "up_to_date"
    assert payload["cleanup_jobs"]["task_name"] == worker_tasks.OPS_CLEANUP_TASK_NAME


def test_migration_status_helper_behaves_for_up_to_date_and_outdated(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(migration_status_module, "_get_head_revisions", lambda: ["rev-002"])
    monkeypatch.setattr(migration_status_module, "_get_current_revisions", lambda db: ["rev-002"])
    up_to_date = migration_status_module.get_migration_status(db_session)
    assert up_to_date["status"] == "up_to_date"
    assert up_to_date["up_to_date"] is True
    assert up_to_date["pending_revisions"] == []

    monkeypatch.setattr(migration_status_module, "_get_current_revisions", lambda db: ["rev-001"])
    outdated = migration_status_module.get_migration_status(db_session)
    assert outdated["status"] == "outdated"
    assert outdated["up_to_date"] is False
    assert outdated["pending_revisions"] == ["rev-002"]


def test_idempotency_cleanup_job_removes_old_keys_and_preserves_recent(
    db_session: Session,
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    old_created_at = now - timedelta(days=30)
    recent_created_at = now - timedelta(days=2)
    old = IdempotencyKey(
        idempotency_key="phase64-old-key",
        scope="phase64",
        request_hash="a" * 64,
        response_status_code=200,
        response_body_json={"ok": True},
        resource_type="appointment",
        resource_id=1,
        created_at=old_created_at,
        updated_at=old_created_at,
    )
    recent = IdempotencyKey(
        idempotency_key="phase64-recent-key",
        scope="phase64",
        request_hash="b" * 64,
        response_status_code=200,
        response_body_json={"ok": True},
        resource_type="appointment",
        resource_id=2,
        created_at=recent_created_at,
        updated_at=recent_created_at,
    )
    db_session.add_all([old, recent])
    db_session.commit()

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    result = worker_tasks.cleanup_operational_data(
        domain_events_retention_days=90,
        idempotency_keys_retention_days=7,
    )
    assert result["idempotency_keys_deleted"] == 1

    remaining = list(db_session.scalars(select(IdempotencyKey).order_by(IdempotencyKey.id.asc())))
    assert len(remaining) == 1
    assert remaining[0].idempotency_key == "phase64-recent-key"


def test_domain_event_cleanup_job_removes_old_events_and_preserves_recent(
    db_session: Session,
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    old_created_at = now - timedelta(days=45)
    recent_created_at = now - timedelta(days=2)
    old_event = DomainEvent(
        event_type="phase64_old_event",
        actor_type="system",
        status="info",
        payload_json={"id": 1},
        created_at=old_created_at,
    )
    recent_event = DomainEvent(
        event_type="phase64_recent_event",
        actor_type="system",
        status="info",
        payload_json={"id": 2},
        created_at=recent_created_at,
    )
    db_session.add_all([old_event, recent_event])
    db_session.commit()

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    result = worker_tasks.cleanup_operational_data(
        domain_events_retention_days=7,
        idempotency_keys_retention_days=90,
    )
    assert result["domain_events_deleted"] == 1

    remaining = list(db_session.scalars(select(DomainEvent).order_by(DomainEvent.id.asc())))
    assert len(remaining) == 1
    assert remaining[0].event_type == "phase64_recent_event"


def test_cleanup_jobs_are_safe_on_repeated_invocation(
    db_session: Session,
    monkeypatch,
) -> None:
    now = datetime.now(timezone.utc)
    stale_event = DomainEvent(
        event_type="phase64_stale_event",
        actor_type="system",
        status="info",
        payload_json={"cleanup": True},
        created_at=now - timedelta(days=30),
    )
    stale_key = IdempotencyKey(
        idempotency_key="phase64-stale-key",
        scope="phase64-repeat",
        request_hash="c" * 64,
        response_status_code=200,
        response_body_json={"ok": True},
        resource_type="appointment",
        resource_id=3,
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=30),
    )
    db_session.add_all([stale_event, stale_key])
    db_session.commit()

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    first = worker_tasks.cleanup_operational_data(
        domain_events_retention_days=7,
        idempotency_keys_retention_days=7,
    )
    second = worker_tasks.cleanup_operational_data(
        domain_events_retention_days=7,
        idempotency_keys_retention_days=7,
    )
    assert first["domain_events_deleted"] == 1
    assert first["idempotency_keys_deleted"] == 1
    assert second["domain_events_deleted"] == 0
    assert second["idempotency_keys_deleted"] == 0


def test_runtime_config_validation_rejects_unsafe_production_combinations(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "prod-webhook-secret")
    monkeypatch.setenv("ENABLE_RATE_LIMITING", "false")
    with pytest.raises(ValueError, match="ENABLE_RATE_LIMITING"):
        Settings(_env_file=None)
