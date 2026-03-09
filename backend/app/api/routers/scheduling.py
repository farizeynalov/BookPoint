from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.provider_repository import ProviderRepository
from app.schemas.scheduling import SlotRead
from app.services.scheduling_service import SchedulingService

router = APIRouter()


@router.get("/providers/{provider_id}/slots", response_model=list[SlotRead])
def get_available_slots(
    provider_id: int,
    start_date: date = Query(...),
    end_date: date = Query(...),
    service_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SlotRead]:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)

    scheduling_service = SchedulingService(db)
    try:
        slots = scheduling_service.get_available_slots(
            provider_id=provider_id,
            start_date=start_date,
            end_date=end_date,
            service_id=service_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [SlotRead.model_validate(slot) for slot in slots]
