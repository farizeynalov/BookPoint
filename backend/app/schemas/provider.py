from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead


class ProviderBase(ORMModel):
    organization_id: int
    user_id: int | None = None
    display_name: str
    title: str | None = None
    bio: str | None = None
    appointment_duration_minutes: int = Field(default=30, gt=0)
    is_active: bool = True


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(ORMModel):
    display_name: str | None = None
    title: str | None = None
    bio: str | None = None
    appointment_duration_minutes: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class ProviderRead(ProviderBase, TimestampRead):
    id: int
