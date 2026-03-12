from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
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
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingSummary:
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.get_booking(booking_id=booking_id, access_token=access_token)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return CustomerBookingSummary.model_validate(payload)


@router.post("/{booking_id}/cancel", response_model=CustomerBookingCancelResponse)
def cancel_customer_booking(
    booking_id: int,
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingCancelResponse:
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.cancel_booking(booking_id=booking_id, access_token=access_token)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CustomerBookingCancelResponse.model_validate(payload)


@router.post("/{booking_id}/reschedule", response_model=CustomerBookingRescheduleResponse)
def reschedule_customer_booking(
    booking_id: int,
    body: CustomerBookingRescheduleRequest,
    access_token: str = Depends(_resolve_access_token),
    db: Session = Depends(get_db),
) -> CustomerBookingRescheduleResponse:
    service = CustomerSelfServiceBookingService(db)
    try:
        payload = service.reschedule_booking(
            booking_id=booking_id,
            access_token=access_token,
            scheduled_start=body.scheduled_start,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return CustomerBookingRescheduleResponse.model_validate(payload)
