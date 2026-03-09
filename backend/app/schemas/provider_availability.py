from datetime import time

from app.schemas.common import ORMModel, TimestampRead


class ProviderAvailabilityBase(ORMModel):
    provider_id: int
    weekday: int
    start_time: time
    end_time: time
    is_active: bool = True


class ProviderAvailabilityCreate(ProviderAvailabilityBase):
    pass


class ProviderAvailabilityUpdate(ORMModel):
    weekday: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class ProviderAvailabilityRead(ProviderAvailabilityBase, TimestampRead):
    id: int
