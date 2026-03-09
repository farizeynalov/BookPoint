from app.models.enums import MembershipRole
from app.schemas.common import ORMModel, TimestampRead


class OrganizationMemberCreate(ORMModel):
    organization_id: int
    user_id: int
    role: MembershipRole


class OrganizationMemberUpdate(ORMModel):
    role: MembershipRole | None = None
    is_active: bool | None = None


class OrganizationMemberRead(TimestampRead):
    id: int
    organization_id: int
    user_id: int
    role: MembershipRole
    is_active: bool
