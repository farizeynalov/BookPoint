from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.discovery import (
    DiscoveryBookingConfirmation,
    DiscoveryBookingCreate,
    DiscoveryLocationRead,
    DiscoveryOrganizationRead,
    DiscoveryProviderRead,
    DiscoveryServiceRead,
    DiscoverySlotRead,
)
from app.services.discovery_service import DiscoveryService

router = APIRouter()


def _raise_discovery_error(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, IntegrityError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Booking conflict")
    raise exc


@router.get("/organizations", response_model=list[DiscoveryOrganizationRead])
def list_discovery_organizations(
    db: Session = Depends(get_db),
) -> list[DiscoveryOrganizationRead]:
    organizations = DiscoveryService(db).list_visible_organizations()
    return [DiscoveryOrganizationRead.model_validate(row) for row in organizations]


@router.get("/organizations/{organization_id}", response_model=DiscoveryOrganizationRead)
def get_discovery_organization(
    organization_id: int,
    db: Session = Depends(get_db),
) -> DiscoveryOrganizationRead:
    organization = DiscoveryService(db).get_visible_organization(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return DiscoveryOrganizationRead.model_validate(organization)


@router.get("/organizations/{organization_id}/locations", response_model=list[DiscoveryLocationRead])
def list_discovery_locations(
    organization_id: int,
    db: Session = Depends(get_db),
) -> list[DiscoveryLocationRead]:
    discovery_service = DiscoveryService(db)
    try:
        locations = discovery_service.list_visible_locations(organization_id)
    except Exception as exc:
        _raise_discovery_error(exc)
    return [DiscoveryLocationRead.model_validate(location) for location in locations]


@router.get("/locations/{location_id}/services", response_model=list[DiscoveryServiceRead])
def list_discovery_services_for_location(
    location_id: int,
    db: Session = Depends(get_db),
) -> list[DiscoveryServiceRead]:
    discovery_service = DiscoveryService(db)
    try:
        services = discovery_service.list_visible_services_for_location(location_id)
    except Exception as exc:
        _raise_discovery_error(exc)
    return [DiscoveryServiceRead.model_validate(service) for service in services]


@router.get(
    "/locations/{location_id}/services/{service_id}/providers",
    response_model=list[DiscoveryProviderRead],
)
def list_discovery_providers_for_service_at_location(
    location_id: int,
    service_id: int,
    db: Session = Depends(get_db),
) -> list[DiscoveryProviderRead]:
    discovery_service = DiscoveryService(db)
    try:
        providers = discovery_service.list_visible_providers_for_service_at_location(
            location_id=location_id,
            service_id=service_id,
        )
    except Exception as exc:
        _raise_discovery_error(exc)
    return [DiscoveryProviderRead.model_validate(provider) for provider in providers]


@router.get("/providers/{provider_id}/slots", response_model=list[DiscoverySlotRead])
def list_discovery_slots(
    provider_id: int,
    service_id: int = Query(...),
    location_id: int = Query(...),
    date_value: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
) -> list[DiscoverySlotRead]:
    discovery_service = DiscoveryService(db)
    try:
        slots = discovery_service.list_visible_slots(
            provider_id=provider_id,
            service_id=service_id,
            location_id=location_id,
            slot_date=date_value,
        )
    except Exception as exc:
        _raise_discovery_error(exc)
    return [DiscoverySlotRead.model_validate(slot) for slot in slots]


@router.post("/bookings", response_model=DiscoveryBookingConfirmation, status_code=status.HTTP_201_CREATED)
def create_discovery_booking(
    payload: DiscoveryBookingCreate,
    db: Session = Depends(get_db),
) -> DiscoveryBookingConfirmation:
    discovery_service = DiscoveryService(db)
    try:
        appointment, customer, payment_summary = discovery_service.create_public_booking(payload)
    except Exception as exc:
        _raise_discovery_error(exc)

    return DiscoveryBookingConfirmation.model_validate(
        {
            "appointment_id": appointment.id,
            "booking_reference": appointment.booking_reference,
            "booking_access_token": appointment.booking_access_token,
            "organization_id": appointment.organization_id,
            "organization_name": appointment.organization.name,
            "location_id": appointment.location_id,
            "location_name": appointment.location.name,
            "provider_id": appointment.provider_id,
            "provider_name": appointment.provider.display_name,
            "service_id": appointment.service_id,
            "service_name": appointment.service.name if appointment.service is not None else None,
            "customer_id": customer.id,
            "scheduled_start": appointment.start_datetime,
            "scheduled_end": appointment.end_datetime,
            "status": appointment.status,
            "payment": payment_summary,
        }
    )
