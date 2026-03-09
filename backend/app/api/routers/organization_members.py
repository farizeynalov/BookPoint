from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationMemberUpdate,
)

router = APIRouter()


@router.post("", response_model=OrganizationMemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    payload: OrganizationMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    org_repo = OrganizationRepository(db)
    user_repo = UserRepository(db)
    member_repo = OrganizationMemberRepository(db)

    organization = org_repo.get(payload.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if user_repo.get_by_id(payload.user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    require_org_membership(
        db,
        organization_id=payload.organization_id,
        user=current_user,
        allowed_roles=[MembershipRole.OWNER, MembershipRole.MANAGER],
    )

    try:
        member = member_repo.add_member(
            organization_id=payload.organization_id,
            user_id=payload.user_id,
            role=payload.role,
        )
    except IntegrityError:
        db.rollback()
        existing = member_repo.get_by_org_and_user(payload.organization_id, payload.user_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not add member")
        member = member_repo.update(existing, role=payload.role, is_active=True)
    return OrganizationMemberRead.model_validate(member)


@router.get("", response_model=list[OrganizationMemberRead])
def list_members(
    organization_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationMemberRead]:
    require_org_membership(db, organization_id=organization_id, user=current_user)
    members = OrganizationMemberRepository(db).list_by_organization(organization_id)
    return [OrganizationMemberRead.model_validate(member) for member in members]


@router.patch("/{member_id}", response_model=OrganizationMemberRead)
def update_member(
    member_id: int,
    payload: OrganizationMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_membership(
        db,
        organization_id=member.organization_id,
        user=current_user,
        allowed_roles=[MembershipRole.OWNER, MembershipRole.MANAGER],
    )
    updated = member_repo.update(member, **payload.model_dump(exclude_unset=True))
    return OrganizationMemberRead.model_validate(updated)


@router.delete("/{member_id}", response_model=OrganizationMemberRead)
def deactivate_member(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_membership(
        db,
        organization_id=member.organization_id,
        user=current_user,
        allowed_roles=[MembershipRole.OWNER, MembershipRole.MANAGER],
    )
    updated = member_repo.update(member, is_active=False)
    return OrganizationMemberRead.model_validate(updated)
