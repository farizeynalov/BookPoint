from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_membership,
    require_provider_schedule_access,
)
from app.models.user import User
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_time_off_repository import ProviderTimeOffRepository
from app.schemas.provider_time_off import (
    ProviderTimeOffCreate,
    ProviderTimeOffRead,
    ProviderTimeOffUpdate,
    ProviderTimeOffWindowCreate,
)
from app.services.provider_time_off_service import ProviderTimeOffService

router = APIRouter()
provider_scoped_router = APIRouter()


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
    require_provider_schedule_access(db, provider=provider, user=current_user)
    try:
        time_off = ProviderTimeOffService(db).create_time_off(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
    interval = ProviderTimeOffRepository(db).get(time_off_id)
    if interval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-off interval not found")

    provider = _load_provider_or_404(interval.provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    try:
        updated = ProviderTimeOffService(db).update_time_off(time_off_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
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
    require_provider_schedule_access(db, provider=provider, user=current_user)
    repo.delete(interval)


@provider_scoped_router.get("/{provider_id}/time-off", response_model=list[ProviderTimeOffRead])
def list_provider_time_off(
    provider_id: int,
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


@provider_scoped_router.post("/{provider_id}/time-off", response_model=ProviderTimeOffRead, status_code=status.HTTP_201_CREATED)
def create_provider_time_off(
    provider_id: int,
    payload: ProviderTimeOffWindowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderTimeOffRead:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    create_payload = ProviderTimeOffCreate(provider_id=provider_id, **payload.model_dump())
    try:
        row = ProviderTimeOffService(db).create_time_off(create_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ProviderTimeOffRead.model_validate(row)


@provider_scoped_router.patch("/{provider_id}/time-off/{time_off_id}", response_model=ProviderTimeOffRead)
def update_provider_time_off(
    provider_id: int,
    time_off_id: int,
    payload: ProviderTimeOffUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderTimeOffRead:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    row = ProviderTimeOffRepository(db).get(time_off_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-off interval not found")
    try:
        updated = ProviderTimeOffService(db).update_time_off(time_off_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ProviderTimeOffRead.model_validate(updated)


@provider_scoped_router.delete("/{provider_id}/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_time_off(
    provider_id: int,
    time_off_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    repo = ProviderTimeOffRepository(db)
    row = repo.get(time_off_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time-off interval not found")
    repo.delete(row)
