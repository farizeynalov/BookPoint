from decimal import Decimal

from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead


class ServiceBase(ORMModel):
    organization_id: int
    provider_id: int | None = None
    name: str
    description: str | None = None
    duration_minutes: int = Field(gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ORMModel):
    provider_id: int | None = None
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceRead(ServiceBase, TimestampRead):
    id: int
