from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_admin_membership,
    require_org_membership,
)
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.organization_location_repository import OrganizationLocationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_earning_repository import ProviderEarningRepository
from app.repositories.provider_location_repository import ProviderLocationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.user_repository import UserRepository
from app.schemas.payout import ProviderEarningRead
from app.schemas.provider import ProviderCreate, ProviderRead, ProviderUpdate

router = APIRouter()
EARNING_VIEW_ROLES = (MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.STAFF)


def _require_provider_earnings_access(db: Session, *, provider, user: User) -> None:
    membership = require_org_membership(db, organization_id=provider.organization_id, user=user)
    if user.is_platform_admin:
        return
    if membership.role in EARNING_VIEW_ROLES:
        return
    if membership.role == MembershipRole.PROVIDER and provider.user_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization role")


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderRead:
    org_repo = OrganizationRepository(db)
    location_repo = OrganizationLocationRepository(db)
    provider_repo = ProviderRepository(db)
    provider_location_repo = ProviderLocationRepository(db)
    user_repo = UserRepository(db)
    member_repo = OrganizationMemberRepository(db)

    organization = org_repo.get(payload.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if payload.user_id is not None and user_repo.get_by_id(payload.user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked user not found")

    require_org_admin_membership(db, organization_id=payload.organization_id, user=current_user)
    try:
        provider = provider_repo.create(**payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider user is already linked")
    active_locations = location_repo.list_by_organization(payload.organization_id, include_inactive=False)
    for location in active_locations:
        existing_assignment = provider_location_repo.get_by_provider_and_location(provider.id, location.id)
        if existing_assignment is None:
            provider_location_repo.create(provider_id=provider.id, location_id=location.id)

    if payload.user_id is not None:
        existing = member_repo.get_by_org_and_user(payload.organization_id, payload.user_id)
        if existing is None:
            member_repo.add_member(
                organization_id=payload.organization_id,
                user_id=payload.user_id,
                role=MembershipRole.PROVIDER,
            )
        elif not existing.is_active:
            member_repo.update(existing, is_active=True)
    return ProviderRead.model_validate(provider)


@router.get("", response_model=list[ProviderRead])
def list_providers(
    organization_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderRead]:
    provider_repo = ProviderRepository(db)
    if organization_id is not None:
        require_org_membership(db, organization_id=organization_id, user=current_user)
        providers = provider_repo.list_providers(organization_id=organization_id)
    elif current_user.is_platform_admin:
        providers = provider_repo.list_providers()
    else:
        org_ids = OrganizationMemberRepository(db).list_active_org_ids_for_user(current_user.id)
        if not org_ids:
            return []
        providers = [provider for provider in provider_repo.list_providers() if provider.organization_id in org_ids]
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


@router.get("/{provider_id}/earnings", response_model=list[ProviderEarningRead])
def list_provider_earnings(
    provider_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderEarningRead]:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    _require_provider_earnings_access(db, provider=provider, user=current_user)
    earnings = ProviderEarningRepository(db).list_by_provider(provider_id)
    return [ProviderEarningRead.model_validate(earning) for earning in earnings]


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
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
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
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
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
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
    return ProviderRead.model_validate(provider_repo.update(provider, is_active=False))
