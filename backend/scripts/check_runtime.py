from __future__ import annotations

import json

from app.core.config import settings
from app.core.health import build_readiness_payload
from app.db.session import SessionLocal
from app.services.operations.migration_status import get_migration_status


def main() -> None:
    _, readiness_payload = build_readiness_payload()
    session = SessionLocal()
    try:
        migration_status = get_migration_status(session)
    finally:
        session.close()

    summary = {
        "environment": settings.resolved_environment,
        "docs_enabled": settings.enable_docs,
        "metrics_enabled": settings.enable_metrics,
        "admin_internal_endpoints_enabled": settings.enable_admin_internal_endpoints,
        "rate_limiting_enabled": settings.enable_rate_limiting,
        "dependencies": readiness_payload.get("checks", {}),
        "migrations": migration_status,
        "cleanup": {
            "domain_events_retention_days": settings.domain_events_retention_days,
            "idempotency_keys_retention_days": settings.idempotency_keys_retention_days,
            "ops_cleanup_interval_seconds": settings.ops_cleanup_interval_seconds,
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
