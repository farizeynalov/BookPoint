from datetime import datetime, timezone

from pydantic import field_serializer, field_validator

from app.models.enums import AppointmentStatus, BookingChannel
from app.schemas.common import ORMModel, TimestampRead


class AppointmentCreate(ORMModel):
    organization_id: int | None = None
    location_id: int
    provider_id: int
    service_id: int | None = None
    customer_id: int
    start_datetime: datetime
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    booking_channel: BookingChannel = BookingChannel.WEB
    notes: str | None = None


class AppointmentReschedule(ORMModel):
    start_datetime: datetime


class AppointmentCancel(ORMModel):
    notes: str | None = None


class AppointmentRead(TimestampRead):
    id: int
    organization_id: int
    location_id: int
    provider_id: int
    service_id: int | None
    customer_id: int
    start_datetime: datetime
    end_datetime: datetime
    status: AppointmentStatus
    booking_channel: BookingChannel
    notes: str | None

    @field_validator("start_datetime", "end_datetime", "created_at", "updated_at", mode="after")
    @classmethod
    def normalize_datetime_to_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @field_serializer("start_datetime", "end_datetime", "created_at", "updated_at")
    def serialize_datetime_with_explicit_utc_offset(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
