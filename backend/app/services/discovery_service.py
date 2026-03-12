from datetime import date, datetime, timezone
import logging

from sqlalchemy import and_, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import AppointmentStatus, BookingChannel
from app.models.organization import Organization
from app.models.organization_location import OrganizationLocation
from app.models.provider import Provider
from app.models.provider_location import ProviderLocation
from app.models.provider_service import ProviderService
from app.models.service import Service
from app.models.service_location import ServiceLocation
from app.repositories.customer_repository import CustomerRepository
from app.repositories.organization_location_repository import OrganizationLocationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_location_repository import ProviderLocationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_service_repository import ProviderServiceRepository
from app.repositories.service_location_repository import ServiceLocationRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.appointment import AppointmentCreate
from app.schemas.discovery import DiscoveryBookingCreate
from app.services.appointment_service import AppointmentService
from app.services.payments.service import PaymentService
from app.services.scheduling_service import SchedulingService
from app.utils.datetime import ensure_aware_utc
from app.utils.phone import normalize_phone_number

logger = logging.getLogger(__name__)


class DiscoveryService:
    def __init__(self, db: Session):
        self.db = db
        self.organization_repo = OrganizationRepository(db)
        self.location_repo = OrganizationLocationRepository(db)
        self.provider_repo = ProviderRepository(db)
        self.provider_location_repo = ProviderLocationRepository(db)
        self.provider_service_repo = ProviderServiceRepository(db)
        self.service_repo = ServiceRepository(db)
        self.service_location_repo = ServiceLocationRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.scheduling_service = SchedulingService(db)
        self.appointment_service = AppointmentService(db)
        self.payment_service = PaymentService(db)

    @staticmethod
    def _normalize_email(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    def list_visible_organizations(self) -> list[Organization]:
        active_location_exists = exists(
            select(OrganizationLocation.id).where(
                OrganizationLocation.organization_id == Organization.id,
                OrganizationLocation.is_active.is_(True),
            )
        )
        stmt = (
            select(Organization)
            .where(
                Organization.is_active.is_(True),
                active_location_exists,
            )
            .order_by(Organization.id.asc())
        )
        return list(self.db.scalars(stmt))

    def get_visible_organization(self, organization_id: int) -> Organization | None:
        stmt = (
            select(Organization)
            .where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
            )
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_visible_locations(self, organization_id: int) -> list[OrganizationLocation]:
        organization = self.get_visible_organization(organization_id)
        if organization is None:
            raise LookupError("Organization not found")
        return self.location_repo.list_by_organization(organization_id, include_inactive=False)

    def get_visible_location(self, location_id: int) -> OrganizationLocation:
        location = self.location_repo.get(location_id)
        if location is None or not location.is_active:
            raise LookupError("Location not found")
        organization = self.get_visible_organization(location.organization_id)
        if organization is None:
            raise LookupError("Location not found")
        return location

    def get_visible_service(self, service_id: int) -> Service:
        service = self.service_repo.get(service_id)
        if service is None or not service.is_active:
            raise LookupError("Service not found")
        organization = self.get_visible_organization(service.organization_id)
        if organization is None:
            raise LookupError("Service not found")
        return service

    def get_visible_provider(self, provider_id: int) -> Provider:
        provider = self.provider_repo.get(provider_id)
        if provider is None or not provider.is_active:
            raise LookupError("Provider not found")
        organization = self.get_visible_organization(provider.organization_id)
        if organization is None:
            raise LookupError("Provider not found")
        return provider

    def list_visible_services_for_location(self, location_id: int) -> list[Service]:
        location = self.get_visible_location(location_id)
        stmt = (
            select(Service)
            .join(ServiceLocation, ServiceLocation.service_id == Service.id)
            .join(ProviderService, ProviderService.service_id == Service.id)
            .join(Provider, Provider.id == ProviderService.provider_id)
            .join(
                ProviderLocation,
                and_(
                    ProviderLocation.provider_id == Provider.id,
                    ProviderLocation.location_id == ServiceLocation.location_id,
                ),
            )
            .where(
                ServiceLocation.location_id == location.id,
                Service.is_active.is_(True),
                Provider.is_active.is_(True),
                Service.organization_id == location.organization_id,
                Provider.organization_id == location.organization_id,
            )
            .distinct()
            .order_by(Service.id.asc())
        )
        return list(self.db.scalars(stmt))

    def list_visible_providers_for_service_at_location(self, *, location_id: int, service_id: int) -> list[Provider]:
        location = self.get_visible_location(location_id)
        service = self.get_visible_service(service_id)
        if service.organization_id != location.organization_id:
            return []
        service_location = self.service_location_repo.get_by_service_and_location(service.id, location.id)
        if service_location is None:
            return []

        stmt = (
            select(Provider)
            .join(ProviderService, ProviderService.provider_id == Provider.id)
            .join(
                ProviderLocation,
                and_(
                    ProviderLocation.provider_id == Provider.id,
                    ProviderLocation.location_id == location.id,
                ),
            )
            .where(
                ProviderService.service_id == service.id,
                Provider.organization_id == location.organization_id,
                Provider.is_active.is_(True),
            )
            .distinct()
            .order_by(Provider.id.asc())
        )
        return list(self.db.scalars(stmt))

    def list_visible_slots(
        self,
        *,
        provider_id: int,
        service_id: int,
        location_id: int,
        slot_date: date,
    ):
        slots = self.scheduling_service.get_available_slots(
            provider_id=provider_id,
            location_id=location_id,
            start_date=slot_date,
            end_date=slot_date,
            service_id=service_id,
        )
        now_utc = datetime.now(timezone.utc)
        return [slot for slot in slots if slot.start_datetime > now_utc]

    def _validate_booking_entities(self, payload: DiscoveryBookingCreate) -> Service:
        organization = self.organization_repo.get(payload.organization_id)
        if organization is None or not organization.is_active:
            raise LookupError("Organization not found")

        location = self.location_repo.get(payload.location_id)
        if location is None or not location.is_active:
            raise LookupError("Location not found")

        provider = self.provider_repo.get(payload.provider_id)
        if provider is None or not provider.is_active:
            raise LookupError("Provider not found")

        service = self.service_repo.get(payload.service_id)
        if service is None or not service.is_active:
            raise LookupError("Service not found")

        if location.organization_id != organization.id:
            raise ValueError("Location does not belong to organization.")
        if provider.organization_id != organization.id:
            raise ValueError("Provider does not belong to organization.")
        if service.organization_id != organization.id:
            raise ValueError("Service does not belong to organization.")

        provider_location = self.provider_location_repo.get_by_provider_and_location(provider.id, location.id)
        if provider_location is None:
            raise ValueError("Provider is not assigned to the selected location.")
        provider_service = self.provider_service_repo.get_by_provider_and_service(provider.id, service.id)
        if provider_service is None:
            raise ValueError("Provider is not assigned to the selected service.")
        service_location = self.service_location_repo.get_by_service_and_location(service.id, location.id)
        if service_location is None:
            raise ValueError("Service is not available at the selected location.")
        return service

    def _candidate_customers_for_contact(self, *, phone_number_normalized: str, email: str | None):
        candidates = []
        customer_from_phone = self.customer_repo.get_by_phone_normalized(phone_number_normalized)
        if customer_from_phone is not None:
            candidates.append(customer_from_phone)
        if email is not None:
            for customer in self.customer_repo.list_by_email(email):
                if all(existing.id != customer.id for existing in candidates):
                    candidates.append(customer)
        return candidates

    def _select_customer_for_organization(self, candidates: list, organization_id: int):
        for customer in candidates:
            if self.customer_repo.has_appointment_in_organization(customer.id, organization_id):
                return customer
        return candidates[0]

    def resolve_or_create_customer(
        self,
        *,
        organization_id: int,
        full_name: str,
        phone_number: str,
        email: str | None,
        preferred_language: str | None,
    ):
        clean_name = full_name.strip()
        if not clean_name:
            raise ValueError("customer_name is required.")

        normalized_phone = normalize_phone_number(phone_number)
        normalized_email = self._normalize_email(email)

        candidates = self._candidate_customers_for_contact(
            phone_number_normalized=normalized_phone,
            email=normalized_email,
        )
        if candidates:
            customer = self._select_customer_for_organization(candidates, organization_id)
            updates = {}
            if customer.full_name != clean_name:
                updates["full_name"] = clean_name
            if normalized_email is not None and customer.email != normalized_email:
                updates["email"] = normalized_email
            if preferred_language is not None and customer.preferred_language != preferred_language:
                updates["preferred_language"] = preferred_language
            if updates:
                customer = self.customer_repo.update(customer, **updates)
            return customer

        try:
            return self.customer_repo.create(
                full_name=clean_name,
                phone_number=phone_number,
                email=normalized_email,
                preferred_language=preferred_language,
            )
        except IntegrityError:
            self.db.rollback()
            existing = self.customer_repo.get_by_phone_normalized(normalized_phone)
            if existing is not None:
                return existing
            raise

    def create_public_booking(self, payload: DiscoveryBookingCreate):
        service = self._validate_booking_entities(payload)
        scheduled_start_utc = ensure_aware_utc(payload.scheduled_start)
        if scheduled_start_utc <= datetime.now(timezone.utc):
            raise ValueError("Scheduled time must be in the future.")

        customer = self.resolve_or_create_customer(
            organization_id=payload.organization_id,
            full_name=payload.customer_name,
            phone_number=payload.customer_phone,
            email=payload.customer_email,
            preferred_language=payload.preferred_language,
        )

        appointment = self.appointment_service.create_appointment(
            AppointmentCreate(
                organization_id=payload.organization_id,
                location_id=payload.location_id,
                provider_id=payload.provider_id,
                service_id=payload.service_id,
                customer_id=customer.id,
                start_datetime=scheduled_start_utc,
                status=AppointmentStatus.PENDING_PAYMENT if service.requires_payment else AppointmentStatus.CONFIRMED,
                booking_channel=BookingChannel.WEB,
                notes=None,
            )
        )
        if service.requires_payment:
            self.payment_service.create_checkout_session_for_appointment(appointment, provider_name="mock")
        payment_summary = self.payment_service.get_customer_payment_summary(appointment)
        logger.info(
            "domain_event=booking_created appointment_id=%s organization_id=%s provider_id=%s service_id=%s payment_required=%s",
            appointment.id,
            appointment.organization_id,
            appointment.provider_id,
            appointment.service_id,
            service.requires_payment,
        )
        return appointment, customer, payment_summary
