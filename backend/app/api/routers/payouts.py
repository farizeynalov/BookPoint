from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi import Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.rate_limit import build_identity_key, enforce_rate_limit
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.provider_earning_repository import ProviderEarningRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.payout import PayoutRead
from app.services.idempotency_service import (
    IDEMPOTENCY_HEADER,
    IdempotencyConflictError,
    IdempotencyService,
    IdempotencyValidationError,
)
from app.services.payments.payout_service import PayoutService

router = APIRouter()


@router.post("/{provider_id}/create", response_model=PayoutRead, status_code=status.HTTP_201_CREATED)
def create_provider_payout(
    provider_id: int,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PayoutRead | JSONResponse:
    idempotency_service = IdempotencyService(db)
    try:
        start_result = idempotency_service.start_request(
            idempotency_key=idempotency_key,
            scope=f"payouts:{provider_id}:create:user:{current_user.id}",
            request_payload={"provider_id": provider_id},
        )
    except IdempotencyValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if start_result.replay_response is not None:
        return start_result.replay_response

    enforce_rate_limit(
        request=request,
        db=db,
        policy_name="payout_create",
        identity_key=build_identity_key([f"user:{current_user.id}", f"provider:{provider_id}"]),
        actor_type="user",
        actor_id=current_user.id,
    )

    try:
        provider = ProviderRepository(db).get(provider_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

        require_org_membership(
            db,
            organization_id=provider.organization_id,
            user=current_user,
            allowed_roles=(MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.STAFF),
        )
        payout_service = PayoutService(db)
        try:
            payout = payout_service.create_payout(
                provider_id=provider_id,
                actor_type="user",
                actor_id=current_user.id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        earning_count = len(ProviderEarningRepository(db).list_by_payout(payout.id))
        response_payload = {
            **PayoutRead.model_validate(payout).model_dump(),
            "earning_count": earning_count,
        }
        response_model = PayoutRead.model_validate(response_payload)
        idempotency_service.finalize_success(
            record=start_result.record,
            status_code=status.HTTP_201_CREATED,
            response_body=response_model.model_dump(mode="json"),
            resource_type="payout",
            resource_id=response_model.id,
        )
        return response_model
    except Exception:
        idempotency_service.abort(record=start_result.record)
        raise
