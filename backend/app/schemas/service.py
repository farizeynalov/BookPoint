from decimal import Decimal

from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead


class ServiceBase(ORMModel):
    name: str
    description: str | None = None
    duration_minutes: int = Field(gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    is_active: bool = True


class ServiceCreate(ServiceBase):
    provider_id: int
    organization_id: int


class ProviderServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ORMModel):
    provider_id: int | None = None
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    buffer_before_minutes: int | None = Field(default=None, ge=0)
    buffer_after_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceRead(ServiceBase, TimestampRead):
    id: int
    organization_id: int
    provider_id: int
