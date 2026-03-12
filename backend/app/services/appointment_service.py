from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import AppointmentStatus
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.organization_location_repository import OrganizationLocationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_location_repository import ProviderLocationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.service_location_repository import ServiceLocationRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.appointment import AppointmentCreate
from app.services.notifications.dispatcher import (
    enqueue_appointment_cancelled_notification,
    enqueue_appointment_created_notification,
    enqueue_appointment_rescheduled_notification,
)
from app.services.scheduling_service import SchedulingService
from app.utils.datetime import ensure_aware_utc

RESCHEDULABLE_STATUSES = {
    AppointmentStatus.PENDING,
    AppointmentStatus.PENDING_PAYMENT,
    AppointmentStatus.CONFIRMED,
}


def _is_overlap_constraint_error(exc: IntegrityError) -> bool:
    error_text = str(getattr(exc, "orig", exc)).lower()
    return "ex_appointments_provider_no_overlap" in error_text


class AppointmentService:
    def __init__(self, db: Session):
        self.db = db
        self.organization_repo = OrganizationRepository(db)
        self.location_repo = OrganizationLocationRepository(db)
        self.provider_repo = ProviderRepository(db)
        self.provider_location_repo = ProviderLocationRepository(db)
        self.service_repo = ServiceRepository(db)
        self.service_location_repo = ServiceLocationRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.appointment_repo = AppointmentRepository(db)
        self.scheduling_service = SchedulingService(db)

    def _resolve_service_timing(self, provider_id: int, service_id: int | None, location_id: int):
        return self.scheduling_service.resolve_service_timing(
            provider_id=provider_id,
            location_id=location_id,
            service_id=service_id,
            require_active_service=True,
            require_active_location=True,
        )

    def _assert_slot_is_available(
        self,
        *,
        provider_id: int,
        location_id: int,
        start_datetime,
        end_datetime,
        service_id: int | None,
    ) -> None:
        provider = self.provider_repo.get(provider_id)
        if provider is None:
            raise ValueError("Provider not found.")
        slot_date = start_datetime.astimezone(ZoneInfo(provider.organization.timezone)).date()
        slots = self.scheduling_service.get_available_slots(
            provider_id=provider_id,
            location_id=location_id,
            start_date=slot_date,
            end_date=slot_date,
            service_id=service_id,
        )
        for slot in slots:
            if slot.start_datetime == start_datetime and slot.end_datetime == end_datetime:
                return
        raise ValueError("Requested time does not fit provider availability.")

    def create_appointment(self, payload: AppointmentCreate):
        start_datetime = ensure_aware_utc(payload.start_datetime)
        try:
            provider = self.provider_repo.get_for_update(payload.provider_id)
            if provider is None or not provider.is_active:
                raise ValueError("Provider not found or inactive.")
            if payload.status not in RESCHEDULABLE_STATUSES:
                raise ValueError("New appointments must be pending or confirmed.")
            organization_id = provider.organization_id

            if payload.organization_id is not None and payload.organization_id != organization_id:
                raise ValueError("organization_id does not match provider organization.")

            organization = self.organization_repo.get(organization_id)
            if organization is None or not organization.is_active:
                raise ValueError("Organization not found or inactive.")

            location = self.location_repo.get(payload.location_id)
            if location is None or not location.is_active:
                raise ValueError("Location not found or inactive.")
            if location.organization_id != organization_id:
                raise ValueError("Provider and location organization mismatch.")
            provider_location = self.provider_location_repo.get_by_provider_and_location(
                provider_id=provider.id,
                location_id=location.id,
            )
            if provider_location is None:
                raise ValueError("Provider is not assigned to the selected location.")

            customer = self.customer_repo.get(payload.customer_id)
            if customer is None:
                raise ValueError("Customer not found.")

            if payload.service_id is not None:
                service = self.service_repo.get(payload.service_id)
                if service is None or not service.is_active:
                    raise ValueError("Service not found or inactive.")
                if service.organization_id != organization_id:
                    raise ValueError("Service and provider organization mismatch.")
                service_location = self.service_location_repo.get_by_service_and_location(
                    service_id=service.id,
                    location_id=location.id,
                )
                if service_location is None:
                    raise ValueError("Service is not available at the selected location.")

            timing = self._resolve_service_timing(provider.id, payload.service_id, payload.location_id)
            end_datetime = start_datetime + timedelta(minutes=timing.visible_duration_minutes)
            blocked_start, blocked_end = self.scheduling_service.compute_blocked_interval(
                visible_start=start_datetime,
                visible_end=end_datetime,
                buffer_before_minutes=timing.buffer_before_minutes,
                buffer_after_minutes=timing.buffer_after_minutes,
            )

            if self.scheduling_service.has_blocked_overlap(
                provider_id=provider.id,
                blocked_start=blocked_start,
                blocked_end=blocked_end,
            ):
                raise ValueError("Provider already has an overlapping appointment.")

            self._assert_slot_is_available(
                provider_id=provider.id,
                location_id=payload.location_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                service_id=payload.service_id,
            )

            appointment = self.appointment_repo.create(
                auto_commit=False,
                organization_id=organization_id,
                location_id=location.id,
                provider_id=provider.id,
                service_id=payload.service_id,
                customer_id=payload.customer_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                status=payload.status,
                booking_channel=payload.booking_channel,
                notes=payload.notes,
            )
            self.db.commit()
            enqueue_appointment_created_notification(appointment.id)
            return appointment
        except IntegrityError as exc:
            self.db.rollback()
            if _is_overlap_constraint_error(exc):
                raise ValueError("Provider already has an overlapping appointment.")
            raise
        except Exception:
            self.db.rollback()
            raise

    def cancel_appointment(self, appointment_id: int, notes: str | None = None):
        try:
            appointment = self.appointment_repo.get_for_update(appointment_id)
            if appointment is None:
                raise ValueError("Appointment not found.")
            provider = self.provider_repo.get_for_update(appointment.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")
            if appointment.status == AppointmentStatus.CANCELLED:
                self.db.commit()
                return appointment
            if appointment.status in {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW}:
                raise ValueError("Completed or no-show appointments cannot be cancelled.")

            merged_notes = notes or appointment.notes
            updated = self.appointment_repo.update(
                appointment,
                auto_commit=False,
                status=AppointmentStatus.CANCELLED,
                notes=merged_notes,
            )
            self.db.commit()
            enqueue_appointment_cancelled_notification(updated.id)
            return updated
        except Exception:
            self.db.rollback()
            raise

    def reschedule_appointment(self, appointment_id: int, new_start_datetime):
        start_datetime = ensure_aware_utc(new_start_datetime)
        try:
            appointment = self.appointment_repo.get_for_update(appointment_id)
            if appointment is None:
                raise ValueError("Appointment not found.")
            if appointment.status not in RESCHEDULABLE_STATUSES:
                raise ValueError("Only pending or confirmed appointments can be rescheduled.")

            provider = self.provider_repo.get_for_update(appointment.provider_id)
            if provider is None or not provider.is_active:
                raise ValueError("Provider not found or inactive.")

            timing = self._resolve_service_timing(
                appointment.provider_id,
                appointment.service_id,
                appointment.location_id,
            )
            end_datetime = start_datetime + timedelta(minutes=timing.visible_duration_minutes)
            blocked_start, blocked_end = self.scheduling_service.compute_blocked_interval(
                visible_start=start_datetime,
                visible_end=end_datetime,
                buffer_before_minutes=timing.buffer_before_minutes,
                buffer_after_minutes=timing.buffer_after_minutes,
            )

            if self.scheduling_service.has_blocked_overlap(
                provider_id=appointment.provider_id,
                blocked_start=blocked_start,
                blocked_end=blocked_end,
                exclude_appointment_id=appointment.id,
            ):
                raise ValueError("Provider already has an overlapping appointment.")

            self._assert_slot_is_available(
                provider_id=appointment.provider_id,
                location_id=appointment.location_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                service_id=appointment.service_id,
            )

            updated = self.appointment_repo.update(
                appointment,
                auto_commit=False,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                status=appointment.status,
            )
            self.db.commit()
            enqueue_appointment_rescheduled_notification(updated.id)
            return updated
        except IntegrityError as exc:
            self.db.rollback()
            if _is_overlap_constraint_error(exc):
                raise ValueError("Provider already has an overlapping appointment.")
            raise
        except Exception:
            self.db.rollback()
            raise
