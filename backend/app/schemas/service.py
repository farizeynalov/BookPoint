from decimal import Decimal

from pydantic import Field, model_validator

from app.models.enums import CancellationPolicyType, PaymentType
from app.schemas.common import ORMModel, TimestampRead
from app.utils.payment import validate_service_payment_policy


class ServiceBase(ORMModel):
    name: str
    description: str | None = None
    duration_minutes: int = Field(gt=0)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    requires_payment: bool = False
    payment_type: PaymentType = PaymentType.FULL
    deposit_amount_minor: int | None = Field(default=None, gt=0)
    cancellation_policy_type: CancellationPolicyType = CancellationPolicyType.FLEXIBLE
    cancellation_window_hours: int = Field(default=24, ge=0)
    buffer_before_minutes: int = Field(default=0, ge=0)
    buffer_after_minutes: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_payment_policy(self):
        validate_service_payment_policy(
            requires_payment=self.requires_payment,
            payment_type=self.payment_type,
            price=self.price,
            currency=self.currency,
            deposit_amount_minor=self.deposit_amount_minor,
        )
        return self


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
    requires_payment: bool | None = None
    payment_type: PaymentType | None = None
    deposit_amount_minor: int | None = Field(default=None, gt=0)
    cancellation_policy_type: CancellationPolicyType | None = None
    cancellation_window_hours: int | None = Field(default=None, ge=0)
    buffer_before_minutes: int | None = Field(default=None, ge=0)
    buffer_after_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ServiceRead(ServiceBase, TimestampRead):
    id: int
    organization_id: int
    provider_id: int
