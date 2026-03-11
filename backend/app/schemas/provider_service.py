from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead
from app.schemas.service import ServiceRead


class ProviderServiceAssignCreate(ORMModel):
    service_id: int
    duration_minutes_override: int | None = Field(default=None, gt=0)


class ProviderServiceAssignUpdate(ORMModel):
    duration_minutes_override: int | None = Field(default=None, gt=0)


class ProviderServiceRead(TimestampRead):
    id: int
    provider_id: int
    service_id: int
    duration_minutes_override: int | None


class ProviderAssignedServiceRead(ServiceRead):
    duration_minutes_override: int | None = None
    effective_duration_minutes: int
