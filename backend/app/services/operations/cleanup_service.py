from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.domain_event_repository import DomainEventRepository
from app.repositories.idempotency_repository import IdempotencyRepository


class OperationalCleanupService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.domain_event_repo = DomainEventRepository(db)
        self.idempotency_repo = IdempotencyRepository(db)

    def cleanup_operational_data(
        self,
        *,
        domain_events_retention_days: int | None = None,
        idempotency_keys_retention_days: int | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, object]:
        now_value = now_utc or datetime.now(timezone.utc)
        domain_days = domain_events_retention_days or settings.domain_events_retention_days
        idempotency_days = idempotency_keys_retention_days or settings.idempotency_keys_retention_days

        domain_cutoff = self._normalize_cutoff_for_db(now_value - timedelta(days=domain_days))
        idempotency_cutoff = self._normalize_cutoff_for_db(now_value - timedelta(days=idempotency_days))

        try:
            deleted_domain_events = self.domain_event_repo.delete_older_than(
                domain_cutoff,
                auto_commit=False,
            )
            deleted_idempotency_keys = self.idempotency_repo.delete_older_than(
                idempotency_cutoff,
                auto_commit=False,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return {
            "domain_events_deleted": deleted_domain_events,
            "idempotency_keys_deleted": deleted_idempotency_keys,
            "domain_events_cutoff": domain_cutoff.isoformat(),
            "idempotency_keys_cutoff": idempotency_cutoff.isoformat(),
        }

    def _normalize_cutoff_for_db(self, cutoff: datetime) -> datetime:
        if self.db.bind is not None and self.db.bind.dialect.name == "sqlite" and cutoff.tzinfo is not None:
            return cutoff.replace(tzinfo=None)
        return cutoff
