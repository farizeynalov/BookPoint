from datetime import datetime, timezone
import secrets

from sqlalchemy.orm import Session

from app.models.enums import AppointmentStatus
from app.repositories.appointment_repository import AppointmentRepository
from app.services.appointment_service import AppointmentService
from app.services.payments.service import PaymentService
from app.utils.datetime import ensure_aware_utc


class CustomerSelfServiceBookingService:
    def __init__(self, db: Session):
        self.db = db
        self.appointment_repo = AppointmentRepository(db)
        self.appointment_service = AppointmentService(db)
        self.payment_service = PaymentService(db)

    def _build_summary(self, appointment) -> dict:
        return {
            "appointment_id": appointment.id,
            "booking_reference": appointment.booking_reference,
            "status": appointment.status,
            "scheduled_start": appointment.start_datetime,
            "scheduled_end": appointment.end_datetime,
            "organization_name": appointment.organization.name,
            "location_name": appointment.location.name,
            "provider_name": appointment.provider.display_name,
            "service_name": appointment.service.name if appointment.service is not None else None,
            "payment": self.payment_service.get_customer_payment_summary(appointment),
        }

    def _get_booking_or_404(self, booking_id: int, access_token: str):
        if not access_token.strip():
            raise LookupError("Booking not found")

        appointment = self.appointment_repo.get(booking_id)
        if appointment is None:
            raise LookupError("Booking not found")

        if not secrets.compare_digest(appointment.booking_access_token, access_token):
            raise LookupError("Booking not found")
        return appointment

    def get_booking(self, *, booking_id: int, access_token: str) -> dict:
        appointment = self._get_booking_or_404(booking_id, access_token)
        return self._build_summary(appointment)

    def cancel_booking(self, *, booking_id: int, access_token: str) -> dict:
        appointment = self._get_booking_or_404(booking_id, access_token)
        if appointment.status == AppointmentStatus.CANCELLED:
            raise ValueError("Booking is already cancelled.")

        updated = self.appointment_service.cancel_appointment(appointment.id, actor_type="customer")
        return self._build_summary(updated)

    def reschedule_booking(self, *, booking_id: int, access_token: str, scheduled_start: datetime) -> dict:
        appointment = self._get_booking_or_404(booking_id, access_token)
        scheduled_start_utc = ensure_aware_utc(scheduled_start)
        if scheduled_start_utc <= datetime.now(timezone.utc):
            raise ValueError("Scheduled time must be in the future.")

        updated = self.appointment_service.reschedule_appointment(
            appointment.id,
            scheduled_start_utc,
            actor_type="customer",
        )
        return self._build_summary(updated)
