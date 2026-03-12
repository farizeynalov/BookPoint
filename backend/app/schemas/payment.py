from datetime import datetime

from pydantic import Field, model_validator

from app.models.enums import PaymentStatus, RefundStatus
from app.schemas.common import ORMModel


class PaymentCheckoutSession(ORMModel):
    provider_name: str
    checkout_session_id: str
    checkout_url: str
    status: PaymentStatus


class BookingPaymentSummary(ORMModel):
    payment_required: bool
    payment_status: PaymentStatus | None = None
    amount_due_minor: int | None = None
    currency: str | None = None
    checkout_url: str | None = None
    checkout_session_id: str | None = None
    provider_name: str | None = None
    expires_at: datetime | None = None
    refund_status: RefundStatus | None = None
    refund_amount_minor: int | None = None
    refund_processed_at: datetime | None = None


class PaymentConfirmRequest(ORMModel):
    provider_name: str = Field(default="mock", min_length=1, max_length=32)
    provider_checkout_session_id: str | None = Field(default=None, max_length=255)
    provider_payment_intent_id: str | None = Field(default=None, max_length=255)
    status: PaymentStatus

    @model_validator(mode="after")
    def _validate_identifiers(self):
        if self.provider_checkout_session_id is None and self.provider_payment_intent_id is None:
            raise ValueError("provider_checkout_session_id or provider_payment_intent_id is required.")
        return self


class PaymentConfirmResponse(ORMModel):
    payment_id: int
    appointment_id: int
    provider_name: str
    status: PaymentStatus
    paid_at: datetime | None = None


class ManualRefundCreate(ORMModel):
    amount_minor: int | None = Field(default=None, ge=0)


class RefundRead(ORMModel):
    id: int
    payment_id: int
    amount_minor: int
    currency: str
    provider_refund_id: str | None = None
    status: RefundStatus
    created_at: datetime
    processed_at: datetime | None = None
