from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus

BLOCKING_STATUSES = (
    AppointmentStatus.PENDING,
    AppointmentStatus.PENDING_PAYMENT,
    AppointmentStatus.CONFIRMED,
)


class AppointmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> Appointment:
        appointment = Appointment(**kwargs)
        self.db.add(appointment)
        self.db.flush()
        self.db.refresh(appointment)
        if auto_commit:
            self.db.commit()
        return appointment

    def get(self, appointment_id: int) -> Appointment | None:
        return self.db.get(Appointment, appointment_id)

    def get_for_update(self, appointment_id: int) -> Appointment | None:
        stmt = select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        return self.db.scalar(stmt)

    def list_appointments(
        self,
        organization_id: int | None = None,
        provider_id: int | None = None,
        customer_id: int | None = None,
    ) -> list[Appointment]:
        stmt = select(Appointment).order_by(Appointment.start_datetime.asc())
        if organization_id is not None:
            stmt = stmt.where(Appointment.organization_id == organization_id)
        if provider_id is not None:
            stmt = stmt.where(Appointment.provider_id == provider_id)
        if customer_id is not None:
            stmt = stmt.where(Appointment.customer_id == customer_id)
        return list(self.db.scalars(stmt))

    def list_by_organization_ids(self, organization_ids: list[int]) -> list[Appointment]:
        if not organization_ids:
            return []
        stmt = (
            select(Appointment)
            .where(Appointment.organization_id.in_(organization_ids))
            .order_by(Appointment.start_datetime.asc())
        )
        return list(self.db.scalars(stmt))

    def has_overlap(
        self,
        *,
        provider_id: int,
        start_datetime: datetime,
        end_datetime: datetime,
        exclude_appointment_id: int | None = None,
    ) -> bool:
        stmt = select(Appointment.id).where(
            Appointment.provider_id == provider_id,
            Appointment.status.in_(BLOCKING_STATUSES),
            Appointment.start_datetime < end_datetime,
            Appointment.end_datetime > start_datetime,
        )
        if exclude_appointment_id is not None:
            stmt = stmt.where(Appointment.id != exclude_appointment_id)
        return self.db.scalar(stmt) is not None

    def list_blocking_for_provider(
        self,
        *,
        provider_id: int,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        exclude_appointment_id: int | None = None,
    ) -> list[Appointment]:
        stmt = select(Appointment).where(
            Appointment.provider_id == provider_id,
            Appointment.status.in_(BLOCKING_STATUSES),
        )
        if start_datetime is not None:
            stmt = stmt.where(Appointment.end_datetime > start_datetime)
        if end_datetime is not None:
            stmt = stmt.where(Appointment.start_datetime < end_datetime)
        if exclude_appointment_id is not None:
            stmt = stmt.where(Appointment.id != exclude_appointment_id)
        return list(self.db.scalars(stmt))

    def list_starting_between(
        self,
        *,
        start_datetime: datetime,
        end_datetime: datetime,
        statuses: tuple[AppointmentStatus, ...] = BLOCKING_STATUSES,
    ) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.status.in_(statuses),
                Appointment.start_datetime >= start_datetime,
                Appointment.start_datetime <= end_datetime,
            )
            .order_by(Appointment.start_datetime.asc())
        )
        return list(self.db.scalars(stmt))

    def list_upcoming_for_customer(
        self,
        *,
        customer_id: int,
        organization_id: int | None = None,
        now_datetime: datetime,
        limit: int = 10,
    ) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.customer_id == customer_id,
                Appointment.status.in_(BLOCKING_STATUSES),
                Appointment.start_datetime >= now_datetime,
            )
            .order_by(Appointment.start_datetime.asc())
            .limit(max(1, min(limit, 50)))
        )
        if organization_id is not None:
            stmt = stmt.where(Appointment.organization_id == organization_id)
        return list(self.db.scalars(stmt))

    def update(self, appointment: Appointment, *, auto_commit: bool = True, **kwargs) -> Appointment:
        for field, value in kwargs.items():
            setattr(appointment, field, value)
        self.db.add(appointment)
        self.db.flush()
        self.db.refresh(appointment)
        if auto_commit:
            self.db.commit()
        return appointment
