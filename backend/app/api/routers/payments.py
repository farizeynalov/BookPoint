from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.payment import PaymentConfirmRequest, PaymentConfirmResponse
from app.services.payments.service import PaymentService

router = APIRouter()


def _require_webhook_secret(
    webhook_secret: str | None = Header(default=None, alias="X-Payment-Webhook-Secret"),
) -> None:
    expected = settings.payment_webhook_secret or settings.secret_key
    if webhook_secret is None or webhook_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook secret")


@router.post("/confirm", response_model=PaymentConfirmResponse)
def confirm_payment_status(
    payload: PaymentConfirmRequest,
    _: None = Depends(_require_webhook_secret),
    db: Session = Depends(get_db),
) -> PaymentConfirmResponse:
    payment_service = PaymentService(db)
    try:
        payment = payment_service.mark_payment_status(
            provider_name=payload.provider_name,
            status=payload.status,
            provider_checkout_session_id=payload.provider_checkout_session_id,
            provider_payment_intent_id=payload.provider_payment_intent_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return PaymentConfirmResponse.model_validate(
        {
            "payment_id": payment.id,
            "appointment_id": payment.appointment_id,
            "provider_name": payment.provider_name,
            "status": payment.status,
            "paid_at": payment.paid_at,
        }
    )
