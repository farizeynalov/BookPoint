from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.enums import AppointmentStatus
from app.schemas.common import ORMModel


class DiscoveryOrganizationRead(ORMModel):
    id: int
    name: str
    slug: str
    business_type: str
    city: str
    timezone: str


class DiscoveryLocationRead(ORMModel):
    id: int
    organization_id: int
    name: str
    slug: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    timezone: str | None = None


class DiscoveryServiceRead(ORMModel):
    id: int
    organization_id: int
    name: str
    description: str | None = None
    duration_minutes: int
    price: Decimal | None = None
    currency: str | None = None


class DiscoveryProviderRead(ORMModel):
    id: int
    organization_id: int
    display_name: str
    title: str | None = None
    bio: str | None = None


class DiscoverySlotRead(ORMModel):
    start_datetime: datetime
    end_datetime: datetime


class DiscoveryBookingCreate(ORMModel):
    organization_id: int
    location_id: int
    provider_id: int
    service_id: int
    scheduled_start: datetime
    customer_name: str = Field(min_length=2, max_length=255)
    customer_phone: str = Field(min_length=7, max_length=32)
    customer_email: str | None = Field(default=None, max_length=255)
    preferred_language: str | None = Field(default="en", max_length=16)


class DiscoveryBookingConfirmation(ORMModel):
    appointment_id: int
    booking_reference: str
    booking_access_token: str
    organization_id: int
    organization_name: str
    location_id: int
    location_name: str
    provider_id: int
    provider_name: str
    service_id: int
    service_name: str | None = None
    customer_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    status: AppointmentStatus


class DiscoverySlotsQuery(ORMModel):
    provider_id: int
    location_id: int
    service_id: int
    date: date
