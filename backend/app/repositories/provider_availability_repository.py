from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider_availability import ProviderAvailability


class ProviderAvailabilityRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> ProviderAvailability:
        availability = ProviderAvailability(**kwargs)
        self.db.add(availability)
        self.db.flush()
        self.db.refresh(availability)
        if auto_commit:
            self.db.commit()
        return availability

    def get(self, availability_id: int) -> ProviderAvailability | None:
        return self.db.get(ProviderAvailability, availability_id)

    def list_by_provider(self, provider_id: int) -> list[ProviderAvailability]:
        stmt = select(ProviderAvailability).where(ProviderAvailability.provider_id == provider_id)
        return list(self.db.scalars(stmt))

    def update(self, availability: ProviderAvailability, *, auto_commit: bool = True, **kwargs) -> ProviderAvailability:
        for field, value in kwargs.items():
            setattr(availability, field, value)
        self.db.add(availability)
        self.db.flush()
        self.db.refresh(availability)
        if auto_commit:
            self.db.commit()
        return availability

    def delete(self, availability: ProviderAvailability) -> None:
        self.db.delete(availability)
        self.db.commit()

    def has_overlap(
        self,
        *,
        provider_id: int,
        weekday: int,
        start_time: time,
        end_time: time,
        exclude_availability_id: int | None = None,
    ) -> bool:
        stmt = select(ProviderAvailability.id).where(
            ProviderAvailability.provider_id == provider_id,
            ProviderAvailability.weekday == weekday,
            ProviderAvailability.is_active.is_(True),
            ProviderAvailability.start_time < end_time,
            ProviderAvailability.end_time > start_time,
        )
        if exclude_availability_id is not None:
            stmt = stmt.where(ProviderAvailability.id != exclude_availability_id)
        return self.db.scalar(stmt) is not None
