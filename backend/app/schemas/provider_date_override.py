from datetime import date, time

from app.schemas.common import ORMModel, TimestampRead


class ProviderDateOverrideBase(ORMModel):
    override_date: date
    start_time: time | None = None
    end_time: time | None = None
    is_available: bool = True
    is_active: bool = True


class ProviderDateOverrideCreate(ProviderDateOverrideBase):
    provider_id: int


class ProviderDateOverrideWindowCreate(ProviderDateOverrideBase):
    pass


class ProviderDateOverrideUpdate(ORMModel):
    override_date: date | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_available: bool | None = None
    is_active: bool | None = None


class ProviderDateOverrideRead(ProviderDateOverrideCreate, TimestampRead):
    id: int
