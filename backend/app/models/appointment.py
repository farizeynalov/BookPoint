from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import AppointmentStatus, BookingChannel


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint("start_datetime < end_datetime", name="ck_appointments_start_before_end"),
        Index("ix_appointments_provider_time_window", "provider_id", "start_datetime", "end_datetime"),
        Index("ix_appointments_org_start", "organization_id", "start_datetime"),
        Index("ix_appointments_customer_start", "customer_id", "start_datetime"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id: Mapped[int] = mapped_column(
        ForeignKey("organization_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status"),
        nullable=False,
        default=AppointmentStatus.PENDING,
        index=True,
    )
    booking_channel: Mapped[BookingChannel] = mapped_column(
        Enum(BookingChannel, name="booking_channel"),
        nullable=False,
        default=BookingChannel.WEB,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    organization = relationship("Organization", back_populates="appointments")
    location = relationship("OrganizationLocation", back_populates="appointments")
    provider = relationship("Provider", back_populates="appointments")
    service = relationship("Service", back_populates="appointments")
    customer = relationship("Customer", back_populates="appointments")
    notifications = relationship("Notification", back_populates="appointment", cascade="all, delete-orphan")
