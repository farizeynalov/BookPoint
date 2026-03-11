from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_membership,
    require_provider_schedule_access,
)
from app.models.user import User
from app.repositories.provider_availability_repository import ProviderAvailabilityRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.provider_availability import (
    ProviderAvailabilityCreate,
    ProviderAvailabilityRead,
    ProviderAvailabilityUpdate,
    ProviderAvailabilityWindowCreate,
)
from app.services.provider_availability_service import ProviderAvailabilityService

router = APIRouter()
provider_scoped_router = APIRouter()


def _load_provider_or_404(provider_id: int, db: Session):
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


@router.post("", response_model=ProviderAvailabilityRead, status_code=status.HTTP_201_CREATED)
def create_availability(
    payload: ProviderAvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderAvailabilityRead:
    provider = _load_provider_or_404(payload.provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)

    try:
        availability = ProviderAvailabilityService(db).create_availability(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Availability block already exists")
    return ProviderAvailabilityRead.model_validate(availability)


@router.get("", response_model=list[ProviderAvailabilityRead])
def list_availability(
    provider_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderAvailabilityRead]:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    blocks = ProviderAvailabilityRepository(db).list_by_provider(provider_id)
    return [ProviderAvailabilityRead.model_validate(block) for block in blocks]


@router.patch("/{availability_id}", response_model=ProviderAvailabilityRead)
def update_availability(
    availability_id: int,
    payload: ProviderAvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderAvailabilityRead:
    availability_repo = ProviderAvailabilityRepository(db)
    block = availability_repo.get(availability_id)
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability block not found")

    provider = _load_provider_or_404(block.provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    try:
        updated = ProviderAvailabilityService(db).update_availability(availability_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Availability block already exists")
    return ProviderAvailabilityRead.model_validate(updated)


@router.delete("/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    availability_repo = ProviderAvailabilityRepository(db)
    block = availability_repo.get(availability_id)
    if block is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability block not found")

    provider = _load_provider_or_404(block.provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    availability_repo.delete(block)


@provider_scoped_router.get("/{provider_id}/availability", response_model=list[ProviderAvailabilityRead])
def list_provider_availability(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderAvailabilityRead]:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    blocks = ProviderAvailabilityRepository(db).list_by_provider(provider_id)
    return [ProviderAvailabilityRead.model_validate(block) for block in blocks]


@provider_scoped_router.post(
    "/{provider_id}/availability",
    response_model=ProviderAvailabilityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_provider_availability(
    provider_id: int,
    payload: ProviderAvailabilityWindowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderAvailabilityRead:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    create_payload = ProviderAvailabilityCreate(provider_id=provider_id, **payload.model_dump())
    try:
        availability = ProviderAvailabilityService(db).create_availability(create_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Availability block already exists")
    return ProviderAvailabilityRead.model_validate(availability)


@provider_scoped_router.patch("/{provider_id}/availability/{availability_id}", response_model=ProviderAvailabilityRead)
def update_provider_availability(
    provider_id: int,
    availability_id: int,
    payload: ProviderAvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderAvailabilityRead:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    availability_repo = ProviderAvailabilityRepository(db)
    block = availability_repo.get(availability_id)
    if block is None or block.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability block not found")
    try:
        updated = ProviderAvailabilityService(db).update_availability(availability_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Availability block already exists")
    return ProviderAvailabilityRead.model_validate(updated)


@provider_scoped_router.delete("/{provider_id}/availability/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_availability(
    provider_id: int,
    availability_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    provider = _load_provider_or_404(provider_id, db)
    require_provider_schedule_access(db, provider=provider, user=current_user)
    availability_repo = ProviderAvailabilityRepository(db)
    block = availability_repo.get(availability_id)
    if block is None or block.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Availability block not found")
    availability_repo.delete(block)
