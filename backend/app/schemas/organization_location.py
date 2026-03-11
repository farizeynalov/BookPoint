from pydantic import Field

from app.schemas.common import ORMModel, TimestampRead


class OrganizationLocationBase(ORMModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool = True


class OrganizationLocationCreate(OrganizationLocationBase):
    pass


class OrganizationLocationUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    address_line_1: str | None = Field(default=None, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class LocationAssignmentCreate(ORMModel):
    location_id: int


class OrganizationLocationRead(OrganizationLocationBase, TimestampRead):
    id: int
    organization_id: int
    slug: str
