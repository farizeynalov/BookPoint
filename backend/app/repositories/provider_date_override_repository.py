from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider_date_override import ProviderDateOverride


class ProviderDateOverrideRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> ProviderDateOverride:
        row = ProviderDateOverride(**kwargs)
        self.db.add(row)
        self.db.flush()
        self.db.refresh(row)
        if auto_commit:
            self.db.commit()
        return row

    def get(self, override_id: int) -> ProviderDateOverride | None:
        return self.db.get(ProviderDateOverride, override_id)

    def list_by_provider(
        self,
        provider_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ProviderDateOverride]:
        stmt = select(ProviderDateOverride).where(ProviderDateOverride.provider_id == provider_id)
        if start_date is not None:
            stmt = stmt.where(ProviderDateOverride.override_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(ProviderDateOverride.override_date <= end_date)
        stmt = stmt.order_by(
            ProviderDateOverride.override_date.asc(),
            ProviderDateOverride.start_time.asc(),
        )
        return list(self.db.scalars(stmt))

    def list_by_provider_and_date(self, provider_id: int, override_date: date) -> list[ProviderDateOverride]:
        stmt = (
            select(ProviderDateOverride)
            .where(
                ProviderDateOverride.provider_id == provider_id,
                ProviderDateOverride.override_date == override_date,
            )
            .order_by(ProviderDateOverride.start_time.asc())
        )
        return list(self.db.scalars(stmt))

    def update(self, row: ProviderDateOverride, *, auto_commit: bool = True, **kwargs) -> ProviderDateOverride:
        for field, value in kwargs.items():
            setattr(row, field, value)
        self.db.add(row)
        self.db.flush()
        self.db.refresh(row)
        if auto_commit:
            self.db.commit()
        return row

    def delete(self, row: ProviderDateOverride) -> None:
        self.db.delete(row)
        self.db.commit()

    def has_overlap(
        self,
        *,
        provider_id: int,
        override_date: date,
        start_time: time,
        end_time: time,
        exclude_override_id: int | None = None,
    ) -> bool:
        stmt = select(ProviderDateOverride.id).where(
            ProviderDateOverride.provider_id == provider_id,
            ProviderDateOverride.override_date == override_date,
            ProviderDateOverride.is_active.is_(True),
            ProviderDateOverride.is_available.is_(True),
            ProviderDateOverride.start_time < end_time,
            ProviderDateOverride.end_time > start_time,
        )
        if exclude_override_id is not None:
            stmt = stmt.where(ProviderDateOverride.id != exclude_override_id)
        return self.db.scalar(stmt) is not None

    def has_active_unavailable_day(
        self,
        *,
        provider_id: int,
        override_date: date,
        exclude_override_id: int | None = None,
    ) -> bool:
        stmt = select(ProviderDateOverride.id).where(
            ProviderDateOverride.provider_id == provider_id,
            ProviderDateOverride.override_date == override_date,
            ProviderDateOverride.is_active.is_(True),
            ProviderDateOverride.is_available.is_(False),
        )
        if exclude_override_id is not None:
            stmt = stmt.where(ProviderDateOverride.id != exclude_override_id)
        return self.db.scalar(stmt) is not None

    def has_active_available_windows(
        self,
        *,
        provider_id: int,
        override_date: date,
        exclude_override_id: int | None = None,
    ) -> bool:
        stmt = select(ProviderDateOverride.id).where(
            ProviderDateOverride.provider_id == provider_id,
            ProviderDateOverride.override_date == override_date,
            ProviderDateOverride.is_active.is_(True),
            ProviderDateOverride.is_available.is_(True),
        )
        if exclude_override_id is not None:
            stmt = stmt.where(ProviderDateOverride.id != exclude_override_id)
        return self.db.scalar(stmt) is not None
