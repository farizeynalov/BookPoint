from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.user_repository import UserRepository
from app.schemas.provider import ProviderCreate, ProviderRead, ProviderUpdate

router = APIRouter()


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    org_repo = OrganizationRepository(db)
    provider_repo = ProviderRepository(db)
    user_repo = UserRepository(db)

    organization = org_repo.get(payload.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if payload.user_id is not None and user_repo.get_by_id(payload.user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked user not found")

    require_org_membership(db, organization_id=payload.organization_id, user=current_user)
    try:
        provider = provider_repo.create(**payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider user is already linked")
    return ProviderRead.model_validate(provider)


@router.get("", response_model=list[ProviderRead])
def list_providers(
    organization_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderRead]:
    if organization_id is not None:
        require_org_membership(db, organization_id=organization_id, user=current_user)
    providers = ProviderRepository(db).list_providers(organization_id=organization_id)
    return [ProviderRead.model_validate(provider) for provider in providers]


@router.get("/{provider_id}", response_model=ProviderRead)
def get_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    return ProviderRead.model_validate(provider)


@router.patch("/{provider_id}", response_model=ProviderRead)
def update_provider(
    provider_id: int,
    payload: ProviderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    provider_repo = ProviderRepository(db)
    provider = provider_repo.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    try:
        updated = provider_repo.update(provider, **payload.model_dump(exclude_unset=True))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider user is already linked")
    return ProviderRead.model_validate(updated)


@router.post("/{provider_id}/activate", response_model=ProviderRead)
def activate_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    provider_repo = ProviderRepository(db)
    provider = provider_repo.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    return ProviderRead.model_validate(provider_repo.update(provider, is_active=True))


@router.post("/{provider_id}/deactivate", response_model=ProviderRead)
def deactivate_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    provider_repo = ProviderRepository(db)
    provider = provider_repo.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    return ProviderRead.model_validate(provider_repo.update(provider, is_active=False))
