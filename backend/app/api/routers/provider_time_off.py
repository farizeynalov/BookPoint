from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_time_off_repository import ProviderTimeOffRepository
from app.schemas.provider_time_off import ProviderTimeOffCreate, ProviderTimeOffRead, ProviderTimeOffUpdate

router = APIRouter()


def _load_provider_or_404(provider_id: int, db: Session):
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


@router.post("", response_model=ProviderTimeOffRead, status_code=status.HTTP_201_CREATED)
def create_time_off(
    payload: ProviderTimeOffCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderTimeOffRead:
    provider = _load_provider_or_404(payload.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    time_off = ProviderTimeOffRepository(db).create(**payload.model_dump())
    return ProviderTimeOffRead.model_validate(time_off)


@router.get("", response_model=list[ProviderTimeOffRead])
def list_time_off(
    provider_id: int = Query(...),
    start_datetime: datetime | None = Query(default=None),
    end_datetime: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderTimeOffRead]:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    rows = ProviderTimeOffRepository(db).list_by_provider(
        provider_id=provider_id,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
    )
    return [ProviderTimeOffRead.model_validate(row) for row in rows]


@router.patch("/{time_off_id}", response_model=ProviderTimeOffRead)
def update_time_off(
    time_off_id: int,
    payload: ProviderTimeOffUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderTimeOffRead:
    repo = ProviderTimeOffRepository(db)
    interval = repo.get(time_off_id)
    if interval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-off interval not found")

    provider = _load_provider_or_404(interval.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    updated = repo.update(interval, **payload.model_dump(exclude_unset=True))
    return ProviderTimeOffRead.model_validate(updated)


@router.delete("/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_time_off(
    time_off_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    repo = ProviderTimeOffRepository(db)
    interval = repo.get(time_off_id)
    if interval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-off interval not found")

    provider = _load_provider_or_404(interval.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    repo.delete(interval)
