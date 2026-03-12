from decimal import Decimal

from pydantic import Field
from pydantic import model_validator

from app.models.enums import CommissionType
from app.schemas.common import ORMModel, TimestampRead
from app.utils.commission import validate_organization_commission_config


class OrganizationBase(ORMModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    business_type: str = Field(default="business", min_length=2, max_length=100)
    city: str = Field(default="Baku", max_length=100)
    address: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Asia/Baku", max_length=64)
    is_active: bool = True
    commission_type: CommissionType = CommissionType.PERCENTAGE
    commission_percentage: Decimal = Field(default=Decimal("0.10"), ge=0, le=1)
    commission_fixed_minor: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_commission_config(self):
        validate_organization_commission_config(
            commission_type=self.commission_type,
            commission_percentage=self.commission_percentage,
            commission_fixed_minor=self.commission_fixed_minor,
        )
        return self


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    business_type: str | None = Field(default=None, min_length=2, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None
    commission_type: CommissionType | None = None
    commission_percentage: Decimal | None = Field(default=None, ge=0, le=1)
    commission_fixed_minor: int | None = Field(default=None, ge=0)


class OrganizationRead(OrganizationBase, TimestampRead):
    id: int
    slug: str
