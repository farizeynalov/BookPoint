from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.provider_earning_repository import ProviderEarningRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.payout import PayoutRead
from app.services.payments.payout_service import PayoutService

router = APIRouter()


@router.post("/{provider_id}/create", response_model=PayoutRead, status_code=status.HTTP_201_CREATED)
def create_provider_payout(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PayoutRead:
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
        payout = payout_service.create_payout(provider_id=provider_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    earning_count = len(ProviderEarningRepository(db).list_by_payout(payout.id))
    payload = {
        **PayoutRead.model_validate(payout).model_dump(),
        "earning_count": earning_count,
    }
    return PayoutRead.model_validate(payload)
