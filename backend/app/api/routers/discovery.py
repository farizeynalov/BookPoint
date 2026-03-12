from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.rate_limit import (
    build_identity_key,
    enforce_rate_limit,
    get_client_ip,
    hash_key_part,
)
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
from app.services.idempotency_service import (
    IDEMPOTENCY_HEADER,
    IdempotencyConflictError,
    IdempotencyService,
    IdempotencyValidationError,
)

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
    request: Request,
    service_id: int = Query(...),
    location_id: int = Query(...),
    date_value: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
) -> list[DiscoverySlotRead]:
    ip = get_client_ip(request)
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="public_slots",
        identity_key=build_identity_key(
            [
                f"ip:{ip}",
                f"provider:{provider_id}",
                f"service:{service_id}",
                f"location:{location_id}",
            ]
        ),
        entity_type="provider",
        entity_id=provider_id,
        actor_type="customer",
    )
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
    request: Request,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    db: Session = Depends(get_db),
) -> DiscoveryBookingConfirmation | JSONResponse:
    idempotency_service = IdempotencyService(db)
    try:
        start_result = idempotency_service.start_request(
            idempotency_key=idempotency_key,
            scope="discovery:create_booking",
            request_payload=payload.model_dump(mode="json"),
        )
    except IdempotencyValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if start_result.replay_response is not None:
        return start_result.replay_response

    ip = get_client_ip(request)
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="public_booking",
        identity_key=build_identity_key([f"ip:{ip}"]),
        actor_type="customer",
    )
    # Duplicate-abuse guard targets rapid re-submission of the same booking intent.
    booking_signature = (
        f"{payload.organization_id}:{payload.location_id}:{payload.provider_id}:"
        f"{payload.service_id}:{payload.scheduled_start.isoformat()}:"
        f"{payload.customer_phone}:{(payload.customer_email or '').strip().lower()}"
    )
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="public_booking_duplicate",
        identity_key=build_identity_key([f"ip:{ip}", f"sig:{hash_key_part(booking_signature)}"]),
        message="Duplicate booking attempt detected. Please retry shortly.",
        actor_type="customer",
    )

    discovery_service = DiscoveryService(db)
    try:
        try:
            appointment, customer, payment_summary = discovery_service.create_public_booking(payload)
        except Exception as exc:
            _raise_discovery_error(exc)

        response_model = DiscoveryBookingConfirmation.model_validate(
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
        idempotency_service.finalize_success(
            record=start_result.record,
            status_code=status.HTTP_201_CREATED,
            response_body=response_model.model_dump(mode="json"),
            resource_type="appointment",
            resource_id=response_model.appointment_id,
        )
        return response_model
    except Exception:
        idempotency_service.abort(record=start_result.record)
        raise
