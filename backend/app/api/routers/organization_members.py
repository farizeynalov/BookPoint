from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_admin_membership,
    require_org_membership,
)
from app.models.user import User
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.schemas.organization_member import (
    OrganizationMemberCreate,
    OrganizationMemberRead,
    OrganizationMemberUpdate,
    OrganizationMembershipCreate,
    OrganizationMembershipUpdate,
)

router = APIRouter()
nested_router = APIRouter()


def _ensure_org_exists(db: Session, organization_id: int):
    organization = OrganizationRepository(db).get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _ensure_user_exists(db: Session, user_id: int):
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _add_or_reactivate_member(
    db: Session,
    *,
    organization_id: int,
    user_id: int,
    role,
):
    member_repo = OrganizationMemberRepository(db)
    try:
        member = member_repo.add_member(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
        )
    except IntegrityError:
        db.rollback()
        existing = member_repo.get_by_org_and_user(organization_id, user_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not add member")
        member = member_repo.update(existing, role=role, is_active=True)
    return member


@router.post("", response_model=OrganizationMemberRead, status_code=status.HTTP_201_CREATED)
def add_member_legacy(
    payload: OrganizationMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    _ensure_org_exists(db, payload.organization_id)
    _ensure_user_exists(db, payload.user_id)
    require_org_admin_membership(db, organization_id=payload.organization_id, user=current_user)
    member = _add_or_reactivate_member(
        db,
        organization_id=payload.organization_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    return OrganizationMemberRead.model_validate(member)


@nested_router.post("/{organization_id}/members", response_model=OrganizationMemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    organization_id: int,
    payload: OrganizationMembershipCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    _ensure_org_exists(db, organization_id)
    _ensure_user_exists(db, payload.user_id)
    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    member = _add_or_reactivate_member(
        db,
        organization_id=organization_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    return OrganizationMemberRead.model_validate(member)


@router.get("", response_model=list[OrganizationMemberRead])
def list_members_legacy(
    organization_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationMemberRead]:
    require_org_membership(db, organization_id=organization_id, user=current_user)
    members = OrganizationMemberRepository(db).list_by_organization(organization_id)
    return [OrganizationMemberRead.model_validate(member) for member in members]


@nested_router.get("/{organization_id}/members", response_model=list[OrganizationMemberRead])
def list_members(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationMemberRead]:
    require_org_membership(db, organization_id=organization_id, user=current_user)
    members = OrganizationMemberRepository(db).list_by_organization(organization_id)
    return [OrganizationMemberRead.model_validate(member) for member in members]


@router.patch("/{member_id}", response_model=OrganizationMemberRead)
def update_member_legacy(
    member_id: int,
    payload: OrganizationMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_admin_membership(db, organization_id=member.organization_id, user=current_user)
    updated = member_repo.update(member, **payload.model_dump(exclude_unset=True))
    return OrganizationMemberRead.model_validate(updated)


@nested_router.patch("/{organization_id}/members/{member_id}", response_model=OrganizationMemberRead)
def update_member(
    organization_id: int,
    member_id: int,
    payload: OrganizationMembershipUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None or member.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    updated = member_repo.update(member, **payload.model_dump(exclude_unset=True))
    return OrganizationMemberRead.model_validate(updated)


@router.delete("/{member_id}", response_model=OrganizationMemberRead)
def deactivate_member_legacy(
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_admin_membership(db, organization_id=member.organization_id, user=current_user)
    updated = member_repo.update(member, is_active=False)
    return OrganizationMemberRead.model_validate(updated)


@nested_router.delete("/{organization_id}/members/{member_id}", response_model=OrganizationMemberRead)
def deactivate_member(
    organization_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationMemberRead:
    member_repo = OrganizationMemberRepository(db)
    member = member_repo.get(member_id)
    if member is None or member.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    updated = member_repo.update(member, is_active=False)
    return OrganizationMemberRead.model_validate(updated)
