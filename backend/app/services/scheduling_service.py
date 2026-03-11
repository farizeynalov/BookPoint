from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.provider_availability_repository import ProviderAvailabilityRepository
from app.repositories.provider_date_override_repository import ProviderDateOverrideRepository
from app.repositories.provider_location_repository import ProviderLocationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_service_repository import ProviderServiceRepository
from app.repositories.provider_time_off_repository import ProviderTimeOffRepository
from app.repositories.service_location_repository import ServiceLocationRepository
from app.repositories.service_repository import ServiceRepository
from app.repositories.organization_location_repository import OrganizationLocationRepository
from app.utils.datetime import daterange


@dataclass(frozen=True)
class Slot:
    start_datetime: datetime
    end_datetime: datetime


@dataclass(frozen=True)
class ServiceTiming:
    visible_duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int

    @property
    def total_block_minutes(self) -> int:
        return self.visible_duration_minutes + self.buffer_before_minutes + self.buffer_after_minutes


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
        self.location_repo = OrganizationLocationRepository(db)
        self.provider_location_repo = ProviderLocationRepository(db)
        self.provider_service_repo = ProviderServiceRepository(db)
        self.service_location_repo = ServiceLocationRepository(db)
        self.availability_repo = ProviderAvailabilityRepository(db)
        self.date_override_repo = ProviderDateOverrideRepository(db)
        self.time_off_repo = ProviderTimeOffRepository(db)
        self.appointment_repo = AppointmentRepository(db)

    def resolve_service_timing(
        self,
        *,
        provider_id: int,
        location_id: int,
        service_id: int | None,
        require_active_service: bool = True,
        require_active_location: bool = True,
    ) -> ServiceTiming:
        provider = self.provider_repo.get(provider_id)
        if provider is None:
            raise ValueError("Provider not found.")

        location = self.location_repo.get(location_id)
        if location is None:
            raise ValueError("Location not found.")
        if require_active_location and not location.is_active:
            raise ValueError("Location not found or inactive.")
        if location.organization_id != provider.organization_id:
            raise ValueError("Provider and location organization mismatch.")

        provider_location = self.provider_location_repo.get_by_provider_and_location(
            provider_id=provider.id,
            location_id=location.id,
        )
        if provider_location is None:
            raise ValueError("Provider is not assigned to the selected location.")

        if service_id is None:
            return ServiceTiming(
                visible_duration_minutes=provider.appointment_duration_minutes,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
            )

        service = self.service_repo.get(service_id)
        if service is None:
            raise ValueError("Service not found or inactive.")
        if require_active_service and not service.is_active:
            raise ValueError("Service not found or inactive.")
        if service.organization_id != provider.organization_id or service.organization_id != location.organization_id:
            raise ValueError("Service, provider, and location organization mismatch.")
        provider_service = self.provider_service_repo.get_by_provider_and_service(
            provider_id=provider.id,
            service_id=service.id,
        )
        if provider_service is None:
            raise ValueError("Provider is not assigned to the selected service.")
        service_location = self.service_location_repo.get_by_service_and_location(
            service_id=service.id,
            location_id=location.id,
        )
        if service_location is None:
            raise ValueError("Service is not available at the selected location.")
        duration_minutes = provider_service.duration_minutes_override or service.duration_minutes
        return ServiceTiming(
            visible_duration_minutes=duration_minutes,
            buffer_before_minutes=service.buffer_before_minutes,
            buffer_after_minutes=service.buffer_after_minutes,
        )

    def _max_provider_buffers(self, provider_id: int) -> tuple[int, int]:
        services = self.service_repo.list_services(provider_id=provider_id, include_inactive=True)
        if not services:
            return 0, 0
        max_before = max(service.buffer_before_minutes for service in services)
        max_after = max(service.buffer_after_minutes for service in services)
        return max_before, max_after

    def _build_service_buffer_lookup(self, appointments) -> dict[int, tuple[int, int]]:
        service_ids = sorted({appointment.service_id for appointment in appointments if appointment.service_id is not None})
        if not service_ids:
            return {}
        services = self.service_repo.get_by_ids(service_ids)
        return {
            service.id: (service.buffer_before_minutes, service.buffer_after_minutes)
            for service in services
        }

    def compute_blocked_interval(
        self,
        *,
        visible_start: datetime,
        visible_end: datetime,
        buffer_before_minutes: int,
        buffer_after_minutes: int,
    ) -> tuple[datetime, datetime]:
        blocked_start = visible_start - timedelta(minutes=buffer_before_minutes)
        blocked_end = visible_end + timedelta(minutes=buffer_after_minutes)
        return blocked_start, blocked_end

    def _appointment_blocked_interval(self, appointment, service_buffer_lookup: dict[int, tuple[int, int]]) -> tuple[datetime, datetime]:
        buffer_before_minutes = 0
        buffer_after_minutes = 0
        if appointment.service_id is not None:
            service_buffers = service_buffer_lookup.get(appointment.service_id)
            if service_buffers is not None:
                buffer_before_minutes, buffer_after_minutes = service_buffers
        return self.compute_blocked_interval(
            visible_start=_as_utc(appointment.start_datetime),
            visible_end=_as_utc(appointment.end_datetime),
            buffer_before_minutes=buffer_before_minutes,
            buffer_after_minutes=buffer_after_minutes,
        )

    def _list_relevant_blocking_appointments(
        self,
        *,
        provider_id: int,
        interval_start: datetime,
        interval_end: datetime,
        exclude_appointment_id: int | None = None,
    ):
        max_before, max_after = self._max_provider_buffers(provider_id)
        query_start = interval_start - timedelta(minutes=max_after)
        query_end = interval_end + timedelta(minutes=max_before)
        return self.appointment_repo.list_blocking_for_provider(
            provider_id=provider_id,
            start_datetime=query_start,
            end_datetime=query_end,
            exclude_appointment_id=exclude_appointment_id,
        )

    def has_blocked_overlap(
        self,
        *,
        provider_id: int,
        blocked_start: datetime,
        blocked_end: datetime,
        exclude_appointment_id: int | None = None,
    ) -> bool:
        appointments = self._list_relevant_blocking_appointments(
            provider_id=provider_id,
            interval_start=blocked_start,
            interval_end=blocked_end,
            exclude_appointment_id=exclude_appointment_id,
        )
        service_buffer_lookup = self._build_service_buffer_lookup(appointments)
        for appointment in appointments:
            appointment_blocked_start, appointment_blocked_end = self._appointment_blocked_interval(
                appointment,
                service_buffer_lookup,
            )
            if _overlaps(blocked_start, blocked_end, appointment_blocked_start, appointment_blocked_end):
                return True
        return False

    def get_available_slots(
        self,
        *,
        provider_id: int,
        location_id: int,
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

        timing = self.resolve_service_timing(
            provider_id=provider_id,
            location_id=location_id,
            service_id=service_id,
            require_active_service=True,
            require_active_location=True,
        )
        visible_duration = timedelta(minutes=timing.visible_duration_minutes)
        buffer_before = timedelta(minutes=timing.buffer_before_minutes)
        buffer_after = timedelta(minutes=timing.buffer_after_minutes)
        timezone_name = provider.organization.timezone
        local_zone = ZoneInfo(timezone_name)

        availabilities = [a for a in self.availability_repo.list_by_provider(provider_id) if a.is_active]
        availability_by_weekday: dict[int, list] = {}
        for availability in availabilities:
            availability_by_weekday.setdefault(availability.weekday, []).append(availability)

        date_overrides = [
            override
            for override in self.date_override_repo.list_by_provider(
                provider_id=provider_id,
                start_date=start_date,
                end_date=end_date,
            )
            if override.is_active
        ]
        overrides_by_date: dict[date, list] = {}
        for override in date_overrides:
            overrides_by_date.setdefault(override.override_date, []).append(override)

        if not availabilities and not date_overrides:
            return []

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
        blocking_appointments = self._list_relevant_blocking_appointments(
            provider_id=provider_id,
            interval_start=range_start_utc,
            interval_end=range_end_utc,
        )
        service_buffer_lookup = self._build_service_buffer_lookup(blocking_appointments)
        for appointment in blocking_appointments:
            blocked_intervals.append(self._appointment_blocked_interval(appointment, service_buffer_lookup))

        slots: list[Slot] = []
        for day in daterange(start_date, end_date):
            override_windows = overrides_by_date.get(day, [])
            if override_windows:
                if any(not override.is_available for override in override_windows):
                    continue
                day_windows = [override for override in override_windows if override.is_available]
            else:
                day_windows = availability_by_weekday.get(day.weekday(), [])
            if not day_windows:
                continue
            for window in day_windows:
                window_start_local = datetime.combine(day, window.start_time).replace(tzinfo=local_zone)
                window_end_local = datetime.combine(day, window.end_time).replace(tzinfo=local_zone)
                window_start = window_start_local.astimezone(timezone.utc)
                window_end = window_end_local.astimezone(timezone.utc)
                cursor = window_start + buffer_before
                while True:
                    candidate_start = cursor
                    candidate_end = candidate_start + visible_duration
                    blocked_start, blocked_end = self.compute_blocked_interval(
                        visible_start=candidate_start,
                        visible_end=candidate_end,
                        buffer_before_minutes=timing.buffer_before_minutes,
                        buffer_after_minutes=timing.buffer_after_minutes,
                    )
                    if blocked_end > window_end:
                        break
                    is_blocked = any(
                        _overlaps(blocked_start, blocked_end, existing_start, existing_end)
                        for existing_start, existing_end in blocked_intervals
                    )
                    if not is_blocked:
                        slots.append(Slot(start_datetime=candidate_start, end_datetime=candidate_end))
                    cursor = candidate_end

        slots.sort(key=lambda s: s.start_datetime)
        return slots
