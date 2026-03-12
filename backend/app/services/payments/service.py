from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AppointmentStatus, PaymentStatus, PaymentType
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.refund_repository import RefundRepository
from app.services.notifications.dispatcher import (
    enqueue_appointment_cancelled_notification,
    enqueue_booking_auto_canceled_payment_timeout_notification,
    enqueue_earning_created_notification,
    enqueue_payment_failed_notification,
    enqueue_payment_required_notification,
    enqueue_payment_succeeded_notification,
)
from app.services.payments.earning_service import EarningService
from app.services.payments.mock_provider import MockCheckoutProvider
from app.utils.payment import decimal_to_minor, validate_service_payment_policy

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.payment_repo = PaymentRepository(db)
        self.refund_repo = RefundRepository(db)
        self.appointment_repo = AppointmentRepository(db)
        self.earning_service = EarningService(db)
        self._providers = {
            "mock": MockCheckoutProvider(),
        }

    @staticmethod
    def _required_amount_minor(service) -> int:
        validate_service_payment_policy(
            requires_payment=service.requires_payment,
            payment_type=service.payment_type,
            price=service.price,
            currency=service.currency,
            deposit_amount_minor=service.deposit_amount_minor,
        )
        if service.payment_type == PaymentType.DEPOSIT:
            return int(service.deposit_amount_minor or 0)
        return decimal_to_minor(service.price, service.currency)  # type: ignore[arg-type]

    def get_latest_payment_for_appointment(self, appointment_id: int):
        return self.payment_repo.get_latest_for_appointment(appointment_id)

    @staticmethod
    def _pending_expires_at(payment) -> datetime:
        created_at = payment.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at + timedelta(minutes=settings.payment_pending_expiration_minutes)

    def get_customer_payment_summary(self, appointment) -> dict:
        service = appointment.service
        if service is None or not service.requires_payment:
            return {
                "payment_required": False,
                "payment_status": None,
                "amount_due_minor": None,
                "currency": None,
                "checkout_url": None,
                "checkout_session_id": None,
                "provider_name": None,
                "expires_at": None,
                "refund_status": None,
                "refund_amount_minor": None,
                "refund_processed_at": None,
            }

        amount_due_minor = self._required_amount_minor(service)
        currency = service.currency.upper() if service.currency else None
        payment = self.payment_repo.get_latest_for_appointment(appointment.id)
        if payment is None:
            return {
                "payment_required": True,
                "payment_status": None,
                "amount_due_minor": amount_due_minor,
                "currency": currency,
                "checkout_url": None,
                "checkout_session_id": None,
                "provider_name": None,
                "expires_at": None,
                "refund_status": None,
                "refund_amount_minor": None,
                "refund_processed_at": None,
            }

        checkout_url = None
        expires_at = None
        if payment.status in {PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION}:
            checkout_url = payment.provider_checkout_url
            expires_at = self._pending_expires_at(payment)
        latest_refund = self.refund_repo.get_latest_for_payment(payment.id)
        return {
            "payment_required": True,
            "payment_status": payment.status,
            "amount_due_minor": payment.amount_minor,
            "currency": payment.currency,
            "checkout_url": checkout_url,
            "checkout_session_id": payment.provider_checkout_session_id,
            "provider_name": payment.provider_name,
            "expires_at": expires_at,
            "refund_status": latest_refund.status if latest_refund is not None else None,
            "refund_amount_minor": latest_refund.amount_minor if latest_refund is not None else None,
            "refund_processed_at": latest_refund.processed_at if latest_refund is not None else None,
        }

    def create_checkout_session_for_appointment(self, appointment, *, provider_name: str = "mock"):
        service = appointment.service
        if service is None or not service.requires_payment:
            return None, None

        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unsupported payment provider: {provider_name}")

        amount_minor = self._required_amount_minor(service)
        currency = (service.currency or "").upper()
        if not currency:
            raise ValueError("Service currency is required for paid bookings.")

        try:
            payment = self.payment_repo.create(
                auto_commit=False,
                appointment_id=appointment.id,
                organization_id=appointment.organization_id,
                amount_minor=amount_minor,
                currency=currency,
                provider_name=provider.name,
                status=PaymentStatus.PENDING,
                payment_type=service.payment_type,
                provider_payment_intent_id=None,
                provider_checkout_session_id=None,
                provider_checkout_url=None,
                paid_at=None,
            )
            checkout_session = provider.create_checkout_session(
                payment_id=payment.id,
                amount_minor=amount_minor,
                currency=currency,
                appointment_id=appointment.id,
            )
            payment = self.payment_repo.update(
                payment,
                auto_commit=False,
                provider_checkout_session_id=checkout_session["checkout_session_id"],
                provider_payment_intent_id=checkout_session["payment_intent_id"],
                provider_checkout_url=checkout_session["checkout_url"],
                status=PaymentStatus(checkout_session["status"]),
            )
            self.db.commit()
            enqueue_payment_required_notification(appointment.id)
            logger.info(
                "domain_event=payment_checkout_created payment_id=%s appointment_id=%s provider=%s",
                payment.id,
                appointment.id,
                payment.provider_name,
            )
            return payment, checkout_session
        except Exception:
            self.db.rollback()
            raise

    def _cancel_pending_payment_appointment(self, appointment, *, reason_note: str) -> bool:
        if appointment.status != AppointmentStatus.PENDING_PAYMENT:
            return False
        merged_notes = appointment.notes or reason_note
        self.appointment_repo.update(
            appointment,
            auto_commit=False,
            status=AppointmentStatus.CANCELLED,
            notes=merged_notes,
        )
        return True

    def _resolve_payment_for_status_update(
        self,
        *,
        provider_name: str,
        provider_checkout_session_id: str | None,
        provider_payment_intent_id: str | None,
    ):
        if provider_checkout_session_id:
            payment = self.payment_repo.get_by_checkout_session_id(provider_checkout_session_id)
        elif provider_payment_intent_id:
            payment = self.payment_repo.get_by_payment_intent_id(provider_payment_intent_id)
        else:
            raise ValueError("Payment identifier is required.")

        if payment is None:
            raise LookupError("Payment not found.")
        if payment.provider_name != provider_name:
            raise LookupError("Payment not found.")
        return payment

    def mark_payment_status(
        self,
        *,
        provider_name: str,
        status: PaymentStatus,
        provider_checkout_session_id: str | None = None,
        provider_payment_intent_id: str | None = None,
    ):
        payment = self._resolve_payment_for_status_update(
            provider_name=provider_name,
            provider_checkout_session_id=provider_checkout_session_id,
            provider_payment_intent_id=provider_payment_intent_id,
        )

        previous_status = payment.status
        logger.info(
            "payment_status_update_requested payment_id=%s previous_status=%s next_status=%s provider=%s",
            payment.id,
            previous_status.value,
            status.value,
            provider_name,
        )
        if previous_status == status:
            logger.info("payment_status_update_skipped_unchanged payment_id=%s status=%s", payment.id, status.value)
            return payment
        if previous_status in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED} and status in {
            PaymentStatus.PENDING,
            PaymentStatus.REQUIRES_ACTION,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELED,
        }:
            logger.warning(
                "payment_status_update_ignored_terminal payment_id=%s previous_status=%s requested_status=%s",
                payment.id,
                previous_status.value,
                status.value,
            )
            return payment

        paid_at = datetime.now(timezone.utc) if status == PaymentStatus.SUCCEEDED else None
        appointment_was_auto_cancelled = False
        earning_created = False

        try:
            payment = self.payment_repo.update(
                payment,
                auto_commit=False,
                status=status,
                paid_at=paid_at,
            )
            appointment = self.appointment_repo.get_for_update(payment.appointment_id)
            if appointment is None:
                raise LookupError("Appointment not found.")

            if status == PaymentStatus.SUCCEEDED:
                if appointment.status in {AppointmentStatus.PENDING_PAYMENT, AppointmentStatus.PENDING}:
                    self.appointment_repo.update(
                        appointment,
                        auto_commit=False,
                        status=AppointmentStatus.CONFIRMED,
                    )
                _, earning_created = self.earning_service.ensure_earning_for_payment(
                    payment=payment,
                    appointment=appointment,
                    auto_commit=False,
                )
            elif status in {PaymentStatus.FAILED, PaymentStatus.CANCELED}:
                appointment_was_auto_cancelled = self._cancel_pending_payment_appointment(
                    appointment,
                    reason_note="Auto-cancelled due to unsuccessful payment.",
                )
            self.db.commit()
            logger.info(
                "domain_event=payment_status_updated payment_id=%s appointment_id=%s previous_status=%s status=%s",
                payment.id,
                payment.appointment_id,
                previous_status.value,
                status.value,
            )
        except Exception:
            self.db.rollback()
            raise

        if earning_created:
            enqueue_earning_created_notification(payment.appointment_id)
        if status != previous_status:
            if status == PaymentStatus.SUCCEEDED:
                enqueue_payment_succeeded_notification(payment.appointment_id)
            elif status in {PaymentStatus.FAILED, PaymentStatus.CANCELED}:
                enqueue_payment_failed_notification(payment.appointment_id)
            if appointment_was_auto_cancelled:
                enqueue_appointment_cancelled_notification(payment.appointment_id)
                logger.info(
                    "domain_event=appointment_auto_canceled_due_to_payment_failure appointment_id=%s payment_id=%s",
                    payment.appointment_id,
                    payment.id,
                )
        return payment

    def expire_pending_payments(
        self,
        *,
        expiration_minutes: int | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, int]:
        effective_now = now_utc or datetime.now(timezone.utc)
        minutes = expiration_minutes if expiration_minutes is not None else settings.payment_pending_expiration_minutes
        cutoff = effective_now - timedelta(minutes=minutes)
        cutoff_for_query = cutoff
        if self.db.bind is not None and self.db.bind.dialect.name == "sqlite" and cutoff_for_query.tzinfo is not None:
            cutoff_for_query = cutoff_for_query.replace(tzinfo=None)
        checked = 0
        expired = 0
        auto_canceled_appointments = 0
        failed = 0

        payments = self.payment_repo.list_expired_pending(cutoff_for_query)
        for stale_payment in payments:
            checked += 1
            try:
                payment = self.payment_repo.get_for_update(stale_payment.id)
                if payment is None:
                    continue
                if payment.status not in {PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION}:
                    continue
                appointment = self.appointment_repo.get_for_update(payment.appointment_id)
                if appointment is None:
                    continue

                self.payment_repo.update(
                    payment,
                    auto_commit=False,
                    status=PaymentStatus.CANCELED,
                    paid_at=None,
                )
                appointment_auto_canceled = self._cancel_pending_payment_appointment(
                    appointment,
                    reason_note="Auto-cancelled due to payment timeout.",
                )
                self.db.commit()

                expired += 1
                if appointment_auto_canceled:
                    auto_canceled_appointments += 1
                    enqueue_appointment_cancelled_notification(appointment.id)
                    enqueue_booking_auto_canceled_payment_timeout_notification(appointment.id)
                    logger.info(
                        "domain_event=appointment_auto_canceled_due_to_payment_timeout appointment_id=%s payment_id=%s",
                        appointment.id,
                        payment.id,
                    )
            except Exception:
                self.db.rollback()
                failed += 1
                logger.exception("payment_expiration_item_failed payment_id=%s", stale_payment.id)
                continue

        return {
            "checked": checked,
            "expired": expired,
            "auto_canceled_appointments": auto_canceled_appointments,
            "failed": failed,
        }
