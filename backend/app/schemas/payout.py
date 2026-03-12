from datetime import datetime

from app.models.enums import PayoutStatus, ProviderEarningStatus
from app.schemas.common import ORMModel


class ProviderEarningRead(ORMModel):
    id: int
    provider_id: int
    appointment_id: int
    payment_id: int
    payout_id: int | None = None
    gross_amount_minor: int
    platform_fee_minor: int
    provider_amount_minor: int
    refunded_amount_minor: int
    adjustment_pending_minor: int
    currency: str
    status: ProviderEarningStatus
    created_at: datetime
    updated_at: datetime


class PayoutRead(ORMModel):
    id: int
    provider_id: int
    total_amount_minor: int
    currency: str
    status: PayoutStatus
    provider_payout_reference: str | None = None
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    earning_count: int = 0
