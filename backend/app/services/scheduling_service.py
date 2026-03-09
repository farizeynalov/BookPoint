from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.provider_availability_repository import ProviderAvailabilityRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_time_off_repository import ProviderTimeOffRepository
from app.repositories.service_repository import ServiceRepository
from app.utils.datetime import daterange


@dataclass(frozen=True)
class Slot:
    start_datetime: datetime
    end_datetime: datetime


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and end_a > start_b


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SchedulingService:
    MAX_QUERY_DAYS = 31

    def __init__(self, db: Session):
        self.db = db
        self.provider_repo = ProviderRepository(db)
        self.service_repo = ServiceRepository(db)
        self.availability_repo = ProviderAvailabilityRepository(db)
        self.time_off_repo = ProviderTimeOffRepository(db)
        self.appointment_repo = AppointmentRepository(db)

    def _resolve_slot_duration_minutes(self, provider_id: int, service_id: int | None) -> int:
        provider = self.provider_repo.get(provider_id)
        if provider is None:
            raise ValueError("Provider not found.")
        if service_id is None:
            return provider.appointment_duration_minutes

        service = self.service_repo.get(service_id)
        if service is None or not service.is_active:
            raise ValueError("Service not found or inactive.")
        if service.organization_id != provider.organization_id:
            raise ValueError("Service and provider organization mismatch.")
        if service.provider_id is not None and service.provider_id != provider.id:
            raise ValueError("Service is restricted to another provider.")
        return service.duration_minutes

    def get_available_slots(
        self,
        *,
        provider_id: int,
        start_date: date,
        end_date: date,
        service_id: int | None = None,
    ) -> list[Slot]:
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date.")
        if (end_date - start_date).days + 1 > self.MAX_QUERY_DAYS:
            raise ValueError(f"Date range cannot exceed {self.MAX_QUERY_DAYS} days.")

        provider = self.provider_repo.get(provider_id)
        if provider is None:
            raise ValueError("Provider not found.")
        if not provider.is_active:
            return []

        slot_duration = timedelta(minutes=self._resolve_slot_duration_minutes(provider_id, service_id))
        timezone_name = provider.organization.timezone
        local_zone = ZoneInfo(timezone_name)

        availabilities = [a for a in self.availability_repo.list_by_provider(provider_id) if a.is_active]
        if not availabilities:
            return []
        availability_by_weekday: dict[int, list] = {}
        for availability in availabilities:
            availability_by_weekday.setdefault(availability.weekday, []).append(availability)

        range_start_local = datetime.combine(start_date, time.min).replace(tzinfo=local_zone)
        range_end_local = datetime.combine(end_date + timedelta(days=1), time.min).replace(tzinfo=local_zone)
        range_start_utc = range_start_local.astimezone(timezone.utc)
        range_end_utc = range_end_local.astimezone(timezone.utc)

        blocked_intervals: list[tuple[datetime, datetime]] = []
        for time_off in self.time_off_repo.list_by_provider(provider_id, range_start_utc, range_end_utc):
            blocked_intervals.append(
                (
                    _as_utc(time_off.start_datetime),
                    _as_utc(time_off.end_datetime),
                )
            )
        for appt in self.appointment_repo.list_blocking_for_provider(
            provider_id=provider_id,
            start_datetime=range_start_utc,
            end_datetime=range_end_utc,
        ):
            blocked_intervals.append((_as_utc(appt.start_datetime), _as_utc(appt.end_datetime)))

        slots: list[Slot] = []
        for day in daterange(start_date, end_date):
            day_windows = availability_by_weekday.get(day.weekday(), [])
            if not day_windows:
                continue
            for window in day_windows:
                window_start_local = datetime.combine(day, window.start_time).replace(tzinfo=local_zone)
                window_end_local = datetime.combine(day, window.end_time).replace(tzinfo=local_zone)
                window_start = window_start_local.astimezone(timezone.utc)
                window_end = window_end_local.astimezone(timezone.utc)
                cursor = window_start
                while cursor + slot_duration <= window_end:
                    candidate_end = cursor + slot_duration
                    is_blocked = any(
                        _overlaps(cursor, candidate_end, blocked_start, blocked_end)
                        for blocked_start, blocked_end in blocked_intervals
                    )
                    if not is_blocked:
                        slots.append(Slot(start_datetime=cursor, end_datetime=candidate_end))
                    cursor = candidate_end

        slots.sort(key=lambda s: s.start_datetime)
        return slots
