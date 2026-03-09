from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import MembershipRole
from app.models.organization_member import OrganizationMember


class OrganizationMemberRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_member(self, organization_id: int, user_id: int, role: MembershipRole) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            is_active=True,
        )
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member

    def get(self, member_id: int) -> OrganizationMember | None:
        return self.db.get(OrganizationMember, member_id)

    def get_by_org_and_user(self, organization_id: int, user_id: int) -> OrganizationMember | None:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        return self.db.scalar(stmt)

    def list_by_organization(self, organization_id: int) -> list[OrganizationMember]:
        stmt = select(OrganizationMember).where(OrganizationMember.organization_id == organization_id)
        return list(self.db.scalars(stmt))

    def list_active_org_ids_for_user(self, user_id: int) -> list[int]:
        stmt = select(OrganizationMember.organization_id).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.is_active.is_(True),
        )
        return list(self.db.scalars(stmt))

    def update(self, member: OrganizationMember, **kwargs) -> OrganizationMember:
        for field, value in kwargs.items():
            setattr(member, field, value)
        self.db.add(member)
        self.db.commit()
        self.db.refresh(member)
        return member
