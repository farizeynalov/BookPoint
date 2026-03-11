from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead


class OrganizationBase(ORMModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    business_type: str = Field(default="business", min_length=2, max_length=100)
    city: str = Field(default="Baku", max_length=100)
    address: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Asia/Baku", max_length=64)
    is_active: bool = True


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    business_type: str | None = Field(default=None, min_length=2, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class OrganizationRead(OrganizationBase, TimestampRead):
    id: int
    slug: str
