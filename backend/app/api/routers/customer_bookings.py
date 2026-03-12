from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.rate_limit import build_identity_key, enforce_rate_limit, get_client_ip, hash_key_part
from app.schemas.customer_self_service import (
    CustomerBookingCancelResponse,
    CustomerBookingRescheduleRequest,
    CustomerBookingRescheduleResponse,
    CustomerBookingSummary,
)
from app.services.customer_self_service_booking_service import CustomerSelfServiceBookingService

router = APIRouter()


def _resolve_access_token(
    query_token: str | None = Query(default=None, alias="access_token"),
    header_token: str | None = Header(default=None, alias="X-Booking-Token"),
) -> str:
    token = header_token or query_token
    if token is None or not token.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking access token is required")
    return token.strip()


@router.get("/{booking_id}", response_model=CustomerBookingSummary)
def get_customer_booking(
    booking_id: int,
    request: Request,
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingSummary:
    ip = get_client_ip(request)
    token_hash = hash_key_part(access_token)
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="customer_booking_get",
        identity_key=build_identity_key([f"ip:{ip}", f"booking:{booking_id}", f"token:{token_hash}"]),
        actor_type="customer",
        entity_type="appointment",
        entity_id=booking_id,
    )
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.get_booking(booking_id=booking_id, access_token=access_token)
    except LookupError as exc:
        enforce_rate_limit(
            request=request,
            db=db,
            policy_name="customer_invalid_token",
            identity_key=build_identity_key([f"ip:{ip}"]),
            message="Too many invalid booking token attempts. Please retry later.",
            actor_type="customer",
            entity_type="appointment",
            entity_id=booking_id,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CustomerBookingSummary.model_validate(payload)


@router.post("/{booking_id}/cancel", response_model=CustomerBookingCancelResponse)
def cancel_customer_booking(
    booking_id: int,
    request: Request,
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingCancelResponse:
    ip = get_client_ip(request)
    token_hash = hash_key_part(access_token)
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="customer_booking_action",
        identity_key=build_identity_key([f"ip:{ip}", f"booking:{booking_id}", f"token:{token_hash}", "action:cancel"]),
        actor_type="customer",
        entity_type="appointment",
        entity_id=booking_id,
    )
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.cancel_booking(booking_id=booking_id, access_token=access_token)
    except LookupError as exc:
        enforce_rate_limit(
            request=request,
            db=db,
            policy_name="customer_invalid_token",
            identity_key=build_identity_key([f"ip:{ip}"]),
            message="Too many invalid booking token attempts. Please retry later.",
            actor_type="customer",
            entity_type="appointment",
            entity_id=booking_id,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CustomerBookingCancelResponse.model_validate(payload)


@router.post("/{booking_id}/reschedule", response_model=CustomerBookingRescheduleResponse)
def reschedule_customer_booking(
    booking_id: int,
    body: CustomerBookingRescheduleRequest,
    request: Request,
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingRescheduleResponse:
    ip = get_client_ip(request)
    token_hash = hash_key_part(access_token)
    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="customer_booking_action",
        identity_key=build_identity_key(
            [f"ip:{ip}", f"booking:{booking_id}", f"token:{token_hash}", "action:reschedule"]
        ),
        actor_type="customer",
        entity_type="appointment",
        entity_id=booking_id,
    )
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.reschedule_booking(
            booking_id=booking_id,
            access_token=access_token,
            scheduled_start=body.scheduled_start,
        )
    except LookupError as exc:
        enforce_rate_limit(
            request=request,
            db=db,
            policy_name="customer_invalid_token",
            identity_key=build_identity_key([f"ip:{ip}"]),
            message="Too many invalid booking token attempts. Please retry later.",
            actor_type="customer",
            entity_type="appointment",
            entity_id=booking_id,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CustomerBookingRescheduleResponse.model_validate(payload)
