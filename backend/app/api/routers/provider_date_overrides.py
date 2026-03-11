from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.provider_date_override_repository import ProviderDateOverrideRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.provider_date_override import (
    ProviderDateOverrideCreate,
    ProviderDateOverrideRead,
    ProviderDateOverrideUpdate,
    ProviderDateOverrideWindowCreate,
)
from app.services.provider_date_override_service import ProviderDateOverrideService

router = APIRouter()
provider_scoped_router = APIRouter()


def _load_provider_or_404(provider_id: int, db: Session):
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


@router.post("", response_model=ProviderDateOverrideRead, status_code=status.HTTP_201_CREATED)
def create_date_override(
    payload: ProviderDateOverrideCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderDateOverrideRead:
    provider = _load_provider_or_404(payload.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    try:
        row = ProviderDateOverrideService(db).create_override(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Date override failed integrity checks")
    return ProviderDateOverrideRead.model_validate(row)


@router.get("", response_model=list[ProviderDateOverrideRead])
def list_date_overrides(
    provider_id: int = Query(...),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderDateOverrideRead]:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    rows = ProviderDateOverrideRepository(db).list_by_provider(
        provider_id=provider_id,
        start_date=start_date,
        end_date=end_date,
    )
    return [ProviderDateOverrideRead.model_validate(row) for row in rows]


@router.patch("/{override_id}", response_model=ProviderDateOverrideRead)
def update_date_override(
    override_id: int,
    payload: ProviderDateOverrideUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderDateOverrideRead:
    repo = ProviderDateOverrideRepository(db)
    row = repo.get(override_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date override not found")
    provider = _load_provider_or_404(row.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    try:
        updated = ProviderDateOverrideService(db).update_override(override_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Date override failed integrity checks")
    return ProviderDateOverrideRead.model_validate(updated)


@router.delete("/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_date_override(
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    repo = ProviderDateOverrideRepository(db)
    row = repo.get(override_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date override not found")
    provider = _load_provider_or_404(row.provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    repo.delete(row)


@provider_scoped_router.get("/{provider_id}/date-overrides", response_model=list[ProviderDateOverrideRead])
def list_date_overrides_for_provider(
    provider_id: int,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderDateOverrideRead]:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    rows = ProviderDateOverrideRepository(db).list_by_provider(
        provider_id=provider_id,
        start_date=start_date,
        end_date=end_date,
    )
    return [ProviderDateOverrideRead.model_validate(row) for row in rows]


@provider_scoped_router.post(
    "/{provider_id}/date-overrides",
    response_model=ProviderDateOverrideRead,
    status_code=status.HTTP_201_CREATED,
)
def create_date_override_for_provider(
    provider_id: int,
    payload: ProviderDateOverrideWindowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderDateOverrideRead:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    create_payload = ProviderDateOverrideCreate(provider_id=provider_id, **payload.model_dump())
    try:
        row = ProviderDateOverrideService(db).create_override(create_payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Date override failed integrity checks")
    return ProviderDateOverrideRead.model_validate(row)


@provider_scoped_router.patch("/{provider_id}/date-overrides/{override_id}", response_model=ProviderDateOverrideRead)
def update_date_override_for_provider(
    provider_id: int,
    override_id: int,
    payload: ProviderDateOverrideUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderDateOverrideRead:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    row = ProviderDateOverrideRepository(db).get(override_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date override not found")
    try:
        updated = ProviderDateOverrideService(db).update_override(override_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Date override failed integrity checks")
    return ProviderDateOverrideRead.model_validate(updated)


@provider_scoped_router.delete("/{provider_id}/date-overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_date_override_for_provider(
    provider_id: int,
    override_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    provider = _load_provider_or_404(provider_id, db)
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    repo = ProviderDateOverrideRepository(db)
    row = repo.get(override_id)
    if row is None or row.provider_id != provider_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Date override not found")
    repo.delete(row)
