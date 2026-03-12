from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.enums import ProviderEarningStatus
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_earning_repository import ProviderEarningRepository
from app.utils.commission import calculate_platform_fee_minor


class EarningService:
    def __init__(self, db: Session):
        self.db = db
        self.organization_repo = OrganizationRepository(db)
        self.earning_repo = ProviderEarningRepository(db)

    def ensure_earning_for_payment(
        self,
        *,
        payment,
        appointment,
        auto_commit: bool = True,
    ):
        existing = self.earning_repo.get_by_payment_id(payment.id)
        if existing is not None:
            return existing, False

        organization = appointment.organization or self.organization_repo.get(appointment.organization_id)
        if organization is None:
            raise LookupError("Organization not found.")

        gross_amount_minor = int(payment.amount_minor)
        platform_fee_minor = calculate_platform_fee_minor(
            amount_minor=gross_amount_minor,
            commission_type=organization.commission_type,
            commission_percentage=organization.commission_percentage,
            commission_fixed_minor=organization.commission_fixed_minor,
        )
        provider_amount_minor = max(gross_amount_minor - platform_fee_minor, 0)

        earning = self.earning_repo.create(
            auto_commit=auto_commit,
            provider_id=appointment.provider_id,
            appointment_id=appointment.id,
            payment_id=payment.id,
            payout_id=None,
            gross_amount_minor=gross_amount_minor,
            platform_fee_minor=platform_fee_minor,
            provider_amount_minor=provider_amount_minor,
            refunded_amount_minor=0,
            adjustment_pending_minor=0,
            currency=payment.currency,
            status=ProviderEarningStatus.READY_FOR_PAYOUT if provider_amount_minor > 0 else ProviderEarningStatus.PENDING,
        )
        return earning, True

    @staticmethod
    def _round_minor(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _provider_refund_impact_minor(self, *, earning, refund_amount_minor: int) -> int:
        if refund_amount_minor <= 0:
            return 0
        if earning.gross_amount_minor <= 0:
            return 0
        original_provider_amount_minor = (
            int(earning.provider_amount_minor)
            + int(earning.refunded_amount_minor)
            + int(earning.adjustment_pending_minor)
        )
        if original_provider_amount_minor <= 0:
            return 0
        proportional = self._round_minor(
            Decimal(refund_amount_minor) * Decimal(original_provider_amount_minor) / Decimal(earning.gross_amount_minor)
        )
        if proportional <= 0:
            proportional = 1
        return proportional

    def apply_refund_adjustment_for_payment(
        self,
        *,
        payment_id: int,
        refund_amount_minor: int,
        auto_commit: bool = True,
    ):
        earning = self.earning_repo.get_by_payment_id_for_update(payment_id)
        if earning is None:
            return None

        impact_minor = self._provider_refund_impact_minor(
            earning=earning,
            refund_amount_minor=refund_amount_minor,
        )
        if impact_minor <= 0:
            return earning

        if earning.status == ProviderEarningStatus.PAID_OUT:
            available_adjustment = max(int(earning.provider_amount_minor) - int(earning.adjustment_pending_minor), 0)
            impact_minor = min(impact_minor, available_adjustment)
            if impact_minor <= 0:
                return earning
            return self.earning_repo.update(
                earning,
                auto_commit=auto_commit,
                adjustment_pending_minor=int(earning.adjustment_pending_minor) + impact_minor,
            )

        available_unpaid = int(earning.provider_amount_minor)
        impact_minor = min(impact_minor, available_unpaid)
        if impact_minor <= 0:
            return earning

        remaining_provider_amount = max(available_unpaid - impact_minor, 0)
        new_status = earning.status
        if remaining_provider_amount == 0:
            new_status = ProviderEarningStatus.PENDING
        return self.earning_repo.update(
            earning,
            auto_commit=auto_commit,
            provider_amount_minor=remaining_provider_amount,
            refunded_amount_minor=int(earning.refunded_amount_minor) + impact_minor,
            status=new_status,
        )

    def list_provider_earnings(self, provider_id: int):
        return self.earning_repo.list_by_provider(provider_id)
