from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging

from sqlalchemy.orm import Session

from app.models.enums import CancellationPolicyType, PaymentStatus, PaymentType, RefundStatus
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.services.notifications.dispatcher import (
    enqueue_refund_failed_notification,
    enqueue_refund_initiated_notification,
    enqueue_refund_succeeded_notification,
)
from app.services.payments.earning_service import EarningService
from app.services.payments.mock_provider import MockRefundProvider

logger = logging.getLogger(__name__)


class RefundService:
    MODERATE_DEFAULT_WINDOW_HOURS = 24
    STRICT_DEFAULT_WINDOW_HOURS = 48

    def __init__(self, db: Session):
        self.db = db
        self.payment_repo = PaymentRepository(db)
        self.refund_repo = RefundRepository(db)
        self.earning_service = EarningService(db)
        self._providers = {
            "mock": MockRefundProvider(),
        }

    @staticmethod
    def _as_utc_aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _round_minor(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def get_refundable_remaining_minor(self, payment) -> int:
        refunded = self.refund_repo.sum_succeeded_amount_for_payment(payment.id)
        return max(int(payment.amount_minor) - refunded, 0)

    def _moderate_late_retained_amount_minor(self, appointment, payment) -> int:
        service = appointment.service
        if payment.payment_type == PaymentType.DEPOSIT:
            return payment.amount_minor
        if service is not None and service.deposit_amount_minor is not None:
            return min(int(service.deposit_amount_minor), int(payment.amount_minor))
        return max(self._round_minor(Decimal(payment.amount_minor) * Decimal("0.20")), 1)

    def calculate_refund_amount(self, appointment, payment, *, now_utc: datetime | None = None) -> int:
        if payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED}:
            return 0
        service = appointment.service
        if service is None or not service.requires_payment:
            return 0

        effective_now = self._as_utc_aware(now_utc or datetime.now(timezone.utc))
        starts_at = self._as_utc_aware(appointment.start_datetime)
        hours_before = (starts_at - effective_now).total_seconds() / 3600

        policy = service.cancellation_policy_type
        if policy == CancellationPolicyType.FLEXIBLE:
            target_amount = int(payment.amount_minor)
        elif policy == CancellationPolicyType.MODERATE:
            window_hours = service.cancellation_window_hours or self.MODERATE_DEFAULT_WINDOW_HOURS
            if hours_before >= window_hours:
                target_amount = int(payment.amount_minor)
            else:
                retained = self._moderate_late_retained_amount_minor(appointment, payment)
                target_amount = max(int(payment.amount_minor) - retained, 0)
        else:
            window_hours = service.cancellation_window_hours or self.STRICT_DEFAULT_WINDOW_HOURS
            if hours_before >= window_hours:
                target_amount = self._round_minor(Decimal(payment.amount_minor) * Decimal("0.50"))
            else:
                target_amount = 0

        remaining = self.get_refundable_remaining_minor(payment)
        return min(max(target_amount, 0), remaining)

    def _get_provider(self, provider_name: str):
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unsupported refund provider: {provider_name}")
        return provider

    def mark_refund_succeeded(self, refund, *, provider_refund_id: str | None = None):
        try:
            locked_refund = self.refund_repo.get_for_update(refund.id)
            if locked_refund is None:
                raise LookupError("Refund not found.")
            if locked_refund.status == RefundStatus.SUCCEEDED:
                self.db.commit()
                return locked_refund
            processed_at = datetime.now(timezone.utc)
            updated = self.refund_repo.update(
                locked_refund,
                auto_commit=False,
                status=RefundStatus.SUCCEEDED,
                provider_refund_id=provider_refund_id or locked_refund.provider_refund_id,
                processed_at=processed_at,
            )
            payment = self.payment_repo.get_for_update(updated.payment_id)
            if payment is not None:
                succeeded_total = self.refund_repo.sum_succeeded_amount_for_payment(payment.id)
                if succeeded_total >= payment.amount_minor:
                    self.payment_repo.update(
                        payment,
                        auto_commit=False,
                        status=PaymentStatus.REFUNDED,
                    )
                self.earning_service.apply_refund_adjustment_for_payment(
                    payment_id=payment.id,
                    refund_amount_minor=int(updated.amount_minor),
                    auto_commit=False,
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        enqueue_refund_succeeded_notification(updated.payment.appointment_id)
        logger.info(
            "domain_event=refund_processed refund_id=%s payment_id=%s status=%s amount_minor=%s",
            updated.id,
            updated.payment_id,
            updated.status.value,
            updated.amount_minor,
        )
        return updated

    def mark_refund_failed(self, refund):
        try:
            locked_refund = self.refund_repo.get_for_update(refund.id)
            if locked_refund is None:
                raise LookupError("Refund not found.")
            if locked_refund.status == RefundStatus.FAILED:
                self.db.commit()
                return locked_refund
            updated = self.refund_repo.update(
                locked_refund,
                auto_commit=False,
                status=RefundStatus.FAILED,
                processed_at=datetime.now(timezone.utc),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        enqueue_refund_failed_notification(updated.payment.appointment_id)
        logger.info(
            "domain_event=refund_processed refund_id=%s payment_id=%s status=%s amount_minor=%s",
            updated.id,
            updated.payment_id,
            updated.status.value,
            updated.amount_minor,
        )
        return updated

    def create_refund(self, payment, amount_minor: int):
        if amount_minor < 0:
            raise ValueError("Refund amount must be non-negative.")
        if amount_minor == 0:
            return None
        if payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED}:
            raise ValueError("Only succeeded payments can be refunded.")
        remaining = self.get_refundable_remaining_minor(payment)
        if amount_minor > remaining:
            raise ValueError("Refund amount exceeds refundable balance.")

        try:
            refund = self.refund_repo.create(
                auto_commit=False,
                payment_id=payment.id,
                amount_minor=amount_minor,
                currency=payment.currency,
                provider_refund_id=None,
                status=RefundStatus.PENDING,
                processed_at=None,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        enqueue_refund_initiated_notification(payment.appointment_id)
        logger.info(
            "domain_event=refund_initiated refund_id=%s payment_id=%s amount_minor=%s",
            refund.id,
            payment.id,
            amount_minor,
        )

        provider = self._get_provider(payment.provider_name)
        try:
            provider_result = provider.create_refund(
                payment_id=payment.id,
                amount_minor=amount_minor,
                currency=payment.currency,
            )
            if provider_result.get("status") == RefundStatus.SUCCEEDED.value:
                return self.mark_refund_succeeded(
                    refund,
                    provider_refund_id=provider_result.get("provider_refund_id"),
                )
            return self.mark_refund_failed(refund)
        except Exception:
            return self.mark_refund_failed(refund)

    def process_refund_for_cancellation(self, appointment, *, now_utc: datetime | None = None):
        payment = self.payment_repo.get_latest_for_appointment(appointment.id)
        if payment is None:
            return None
        if payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED}:
            return None
        amount_minor = self.calculate_refund_amount(appointment, payment, now_utc=now_utc)
        if amount_minor <= 0:
            return None
        return self.create_refund(payment, amount_minor)
