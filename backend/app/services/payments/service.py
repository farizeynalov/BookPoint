from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.enums import AppointmentStatus, PaymentStatus, PaymentType
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.payment_repository import PaymentRepository
from app.services.notifications.dispatcher import (
    enqueue_payment_failed_notification,
    enqueue_payment_succeeded_notification,
)
from app.services.payments.mock_provider import MockCheckoutProvider
from app.utils.payment import decimal_to_minor, validate_service_payment_policy


class PaymentService:
    def __init__(self, db: Session):
        self.db = db
        self.payment_repo = PaymentRepository(db)
        self.appointment_repo = AppointmentRepository(db)
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
            }

        checkout_url = None
        if payment.status in {PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION}:
            checkout_url = payment.provider_checkout_url
        return {
            "payment_required": True,
            "payment_status": payment.status,
            "amount_due_minor": payment.amount_minor,
            "currency": payment.currency,
            "checkout_url": checkout_url,
            "checkout_session_id": payment.provider_checkout_session_id,
            "provider_name": payment.provider_name,
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
            return payment, checkout_session
        except Exception:
            self.db.rollback()
            raise

    def mark_payment_status(
        self,
        *,
        provider_name: str,
        status: PaymentStatus,
        provider_checkout_session_id: str | None = None,
        provider_payment_intent_id: str | None = None,
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

        previous_status = payment.status
        paid_at = datetime.now(timezone.utc) if status == PaymentStatus.SUCCEEDED else None

        try:
            payment = self.payment_repo.update(
                payment,
                auto_commit=False,
                status=status,
                paid_at=paid_at,
            )
            if status == PaymentStatus.SUCCEEDED:
                appointment = self.appointment_repo.get_for_update(payment.appointment_id)
                if appointment is None:
                    raise LookupError("Appointment not found.")
                if appointment.status == AppointmentStatus.PENDING:
                    self.appointment_repo.update(
                        appointment,
                        auto_commit=False,
                        status=AppointmentStatus.CONFIRMED,
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        if status != previous_status:
            if status == PaymentStatus.SUCCEEDED:
                enqueue_payment_succeeded_notification(payment.appointment_id)
            elif status == PaymentStatus.FAILED:
                enqueue_payment_failed_notification(payment.appointment_id)
        return payment
