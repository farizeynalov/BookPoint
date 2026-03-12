from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain_event import DomainEvent


class DomainEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> DomainEvent:
        event = DomainEvent(**kwargs)
        self.db.add(event)
        self.db.flush()
        self.db.refresh(event)
        if auto_commit:
            self.db.commit()
        return event

    def get(self, event_id: int) -> DomainEvent | None:
        return self.db.get(DomainEvent, event_id)

    def list_events(
        self,
        *,
        event_type: str | None = None,
        organization_id: int | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[DomainEvent]:
        stmt = select(DomainEvent)
        if event_type is not None:
            stmt = stmt.where(DomainEvent.event_type == event_type)
        if organization_id is not None:
            stmt = stmt.where(DomainEvent.organization_id == organization_id)
        if entity_type is not None:
            stmt = stmt.where(DomainEvent.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(DomainEvent.entity_id == entity_id)
        if status is not None:
            stmt = stmt.where(DomainEvent.status == status)
        if date_from is not None:
            stmt = stmt.where(DomainEvent.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(DomainEvent.created_at <= date_to)
        stmt = stmt.order_by(DomainEvent.created_at.desc(), DomainEvent.id.desc()).limit(max(1, min(limit, 500)))
        return list(self.db.scalars(stmt))

    def delete_older_than(self, cutoff_datetime: datetime, *, auto_commit: bool = True) -> int:
        stmt = delete(DomainEvent).where(DomainEvent.created_at < cutoff_datetime)
        result = self.db.execute(stmt)
        deleted = int(result.rowcount or 0)
        if auto_commit:
            self.db.commit()
        return deleted
