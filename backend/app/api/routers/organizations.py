from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_admin_membership,
    require_org_membership,
)
from app.models.enums import MembershipRole
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate

router = APIRouter()


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationRead:
    org_repo = OrganizationRepository(db)
    member_repo = OrganizationMemberRepository(db)
    organization = org_repo.create(**payload.model_dump())

    existing = member_repo.get_by_org_and_user(organization.id, current_user.id)
    if existing is None:
        member_repo.add_member(organization_id=organization.id, user_id=current_user.id, role=MembershipRole.OWNER)
    return OrganizationRead.model_validate(organization)


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationRead]:
    org_repo = OrganizationRepository(db)
    member_repo = OrganizationMemberRepository(db)
    if current_user.is_platform_admin:
        organizations = org_repo.list_all()
    else:
        org_ids = member_repo.list_active_org_ids_for_user(current_user.id)
        if not org_ids:
            return []
        stmt = select(Organization).where(Organization.id.in_(org_ids)).order_by(Organization.id.asc())
        organizations = list(db.scalars(stmt))
    return [OrganizationRead.model_validate(org) for org in organizations]


@router.get("/{organization_id}", response_model=OrganizationRead)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationRead:
    org_repo = OrganizationRepository(db)
    organization = org_repo.get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    require_org_membership(db, organization_id=organization_id, user=current_user)
    return OrganizationRead.model_validate(organization)


@router.patch("/{organization_id}", response_model=OrganizationRead)
def update_organization(
    organization_id: int,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationRead:
    org_repo = OrganizationRepository(db)
    organization = org_repo.get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    updated = org_repo.update(organization, **payload.model_dump(exclude_unset=True))
    return OrganizationRead.model_validate(updated)


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    org_repo = OrganizationRepository(db)
    organization = org_repo.get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    org_repo.delete(organization)
