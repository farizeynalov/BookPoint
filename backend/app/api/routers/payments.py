from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.schemas.payment import ManualRefundCreate, PaymentConfirmRequest, PaymentConfirmResponse, RefundRead
from app.services.idempotency_service import (
    IDEMPOTENCY_HEADER,
    IdempotencyConflictError,
    IdempotencyService,
    IdempotencyValidationError,
)
from app.services.payments.refund_service import RefundService
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
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    _: None = Depends(_require_webhook_secret),
    db: Session = Depends(get_db),
) -> PaymentConfirmResponse | JSONResponse:
    idempotency_service = IdempotencyService(db)
    try:
        start_result = idempotency_service.start_request(
            idempotency_key=idempotency_key,
            scope="payments:confirm",
            request_payload=payload.model_dump(mode="json"),
        )
    except IdempotencyValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if start_result.replay_response is not None:
        return start_result.replay_response

    payment_service = PaymentService(db)
    try:
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

        response_model = PaymentConfirmResponse.model_validate(
            {
                "payment_id": payment.id,
                "appointment_id": payment.appointment_id,
                "provider_name": payment.provider_name,
                "status": payment.status,
                "paid_at": payment.paid_at,
            }
        )
        idempotency_service.finalize_success(
            record=start_result.record,
            status_code=status.HTTP_200_OK,
            response_body=response_model.model_dump(mode="json"),
            resource_type="payment",
            resource_id=response_model.payment_id,
        )
        return response_model
    except Exception:
        idempotency_service.abort(record=start_result.record)
        raise


@router.post("/{payment_id}/refund", response_model=RefundRead)
def create_manual_refund(
    payment_id: int,
    payload: ManualRefundCreate,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RefundRead | JSONResponse:
    idempotency_service = IdempotencyService(db)
    try:
        start_result = idempotency_service.start_request(
            idempotency_key=idempotency_key,
            scope=f"payments:{payment_id}:manual_refund:user:{current_user.id}",
            request_payload={
                "payment_id": payment_id,
                **payload.model_dump(mode="json"),
            },
        )
    except IdempotencyValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if start_result.replay_response is not None:
        return start_result.replay_response

    try:
        payment = PaymentRepository(db).get(payment_id)
        if payment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

        require_org_membership(
            db,
            organization_id=payment.organization_id,
            user=current_user,
            allowed_roles=(MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.STAFF),
        )

        refund_service = RefundService(db)
        amount_minor = payload.amount_minor
        if amount_minor is None:
            amount_minor = refund_service.get_refundable_remaining_minor(payment)
        try:
            refund = refund_service.create_refund(payment, amount_minor)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if refund is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No refundable amount remaining")
        response_model = RefundRead.model_validate(refund)
        idempotency_service.finalize_success(
            record=start_result.record,
            status_code=status.HTTP_200_OK,
            response_body=response_model.model_dump(mode="json"),
            resource_type="refund",
            resource_id=response_model.id,
        )
        return response_model
    except Exception:
        idempotency_service.abort(record=start_result.record)
        raise
