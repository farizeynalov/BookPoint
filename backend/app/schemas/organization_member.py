from app.models.enums import MembershipRole
from app.schemas.common import ORMModel, TimestampRead


class OrganizationMembershipCreate(ORMModel):
    user_id: int
    role: MembershipRole


class OrganizationMemberCreate(ORMModel):
    organization_id: int
    user_id: int
    role: MembershipRole


class OrganizationMembershipUpdate(ORMModel):
    role: MembershipRole | None = None
    is_active: bool | None = None


class OrganizationMemberUpdate(OrganizationMembershipUpdate):
    pass


class OrganizationMembershipRead(TimestampRead):
    id: int
    organization_id: int
    user_id: int
    role: MembershipRole
    is_active: bool


class OrganizationMemberRead(OrganizationMembershipRead):
    pass
