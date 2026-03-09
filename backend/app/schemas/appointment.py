from datetime import datetime

from app.models.enums import AppointmentStatus, BookingChannel
from app.schemas.common import ORMModel, TimestampRead


class AppointmentCreate(ORMModel):
    organization_id: int | None = None
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
    provider_id: int
    service_id: int | None
    customer_id: int
    start_datetime: datetime
    end_datetime: datetime
    status: AppointmentStatus
    booking_channel: BookingChannel
    notes: str | None
