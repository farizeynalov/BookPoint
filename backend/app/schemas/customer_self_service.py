from datetime import datetime

from app.models.enums import AppointmentStatus
from app.schemas.common import ORMModel
from app.schemas.payment import BookingPaymentSummary


class CustomerBookingSummary(ORMModel):
    appointment_id: int
    booking_reference: str
    status: AppointmentStatus
    scheduled_start: datetime
    scheduled_end: datetime
    organization_name: str
    location_name: str
    provider_name: str
    service_name: str | None = None
    payment: BookingPaymentSummary | None = None


class CustomerBookingCancelResponse(CustomerBookingSummary):
    pass


class CustomerBookingRescheduleRequest(ORMModel):
    scheduled_start: datetime


class CustomerBookingRescheduleResponse(CustomerBookingSummary):
    pass
