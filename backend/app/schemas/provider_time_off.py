from datetime import datetime

from app.schemas.common import ORMModel, TimestampRead


class ProviderTimeOffBase(ORMModel):
    start_datetime: datetime
    end_datetime: datetime
    reason: str | None = None


class ProviderTimeOffCreate(ProviderTimeOffBase):
    provider_id: int


class ProviderTimeOffWindowCreate(ProviderTimeOffBase):
    pass


class ProviderTimeOffUpdate(ORMModel):
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    reason: str | None = None


class ProviderTimeOffRead(ProviderTimeOffCreate, TimestampRead):
    id: int
