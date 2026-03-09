from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider_time_off import ProviderTimeOff


class ProviderTimeOffRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> ProviderTimeOff:
        time_off = ProviderTimeOff(**kwargs)
        self.db.add(time_off)
        self.db.commit()
        self.db.refresh(time_off)
        return time_off

    def get(self, time_off_id: int) -> ProviderTimeOff | None:
        return self.db.get(ProviderTimeOff, time_off_id)

    def list_by_provider(
        self,
        provider_id: int,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> list[ProviderTimeOff]:
        stmt = select(ProviderTimeOff).where(ProviderTimeOff.provider_id == provider_id)
        if start_datetime is not None:
            stmt = stmt.where(ProviderTimeOff.end_datetime > start_datetime)
        if end_datetime is not None:
            stmt = stmt.where(ProviderTimeOff.start_datetime < end_datetime)
        return list(self.db.scalars(stmt))

    def update(self, time_off: ProviderTimeOff, **kwargs) -> ProviderTimeOff:
        for field, value in kwargs.items():
            setattr(time_off, field, value)
        self.db.add(time_off)
        self.db.commit()
        self.db.refresh(time_off)
        return time_off

    def delete(self, time_off: ProviderTimeOff) -> None:
        self.db.delete(time_off)
        self.db.commit()
