from sqlalchemy.orm import Session

from app.repositories.provider_date_override_repository import ProviderDateOverrideRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.provider_date_override import ProviderDateOverrideCreate, ProviderDateOverrideUpdate


class ProviderDateOverrideService:
    def __init__(self, db: Session):
        self.db = db
        self.provider_repo = ProviderRepository(db)
        self.override_repo = ProviderDateOverrideRepository(db)

    def _validate_override_payload(
        self,
        *,
        provider_id: int,
        override_date,
        is_available: bool,
        start_time,
        end_time,
        is_active: bool,
        exclude_override_id: int | None = None,
    ) -> None:
        if is_available:
            if start_time is None or end_time is None:
                raise ValueError("Available date override requires start_time and end_time.")
            if start_time >= end_time:
                raise ValueError("Date override start_time must be before end_time.")
            if is_active and self.override_repo.has_active_unavailable_day(
                provider_id=provider_id,
                override_date=override_date,
                exclude_override_id=exclude_override_id,
            ):
                raise ValueError("Cannot add working-hours override because this date is marked unavailable.")
            if is_active and self.override_repo.has_overlap(
                provider_id=provider_id,
                override_date=override_date,
                start_time=start_time,
                end_time=end_time,
                exclude_override_id=exclude_override_id,
            ):
                raise ValueError("Overlapping date-override window exists for this provider and date.")
            return

        if start_time is not None or end_time is not None:
            raise ValueError("Full-day unavailability override must not include start_time or end_time.")
        if is_active and self.override_repo.has_active_available_windows(
            provider_id=provider_id,
            override_date=override_date,
            exclude_override_id=exclude_override_id,
        ):
            raise ValueError("Cannot mark date unavailable while active working-hour overrides exist for this date.")
        if is_active and self.override_repo.has_active_unavailable_day(
            provider_id=provider_id,
            override_date=override_date,
            exclude_override_id=exclude_override_id,
        ):
            raise ValueError("Full-day unavailability override already exists for this date.")

    def create_override(self, payload: ProviderDateOverrideCreate):
        try:
            provider = self.provider_repo.get_for_update(payload.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")

            self._validate_override_payload(
                provider_id=payload.provider_id,
                override_date=payload.override_date,
                is_available=payload.is_available,
                start_time=payload.start_time,
                end_time=payload.end_time,
                is_active=payload.is_active,
            )

            row = self.override_repo.create(auto_commit=False, **payload.model_dump())
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise

    def update_override(self, override_id: int, payload: ProviderDateOverrideUpdate):
        try:
            row = self.override_repo.get(override_id)
            if row is None:
                raise ValueError("Date override not found.")

            provider = self.provider_repo.get_for_update(row.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")

            updates = payload.model_dump(exclude_unset=True)
            target_date = updates.get("override_date", row.override_date)
            target_is_available = updates.get("is_available", row.is_available)
            target_start = updates.get("start_time", row.start_time)
            target_end = updates.get("end_time", row.end_time)
            target_is_active = updates.get("is_active", row.is_active)

            self._validate_override_payload(
                provider_id=row.provider_id,
                override_date=target_date,
                is_available=target_is_available,
                start_time=target_start,
                end_time=target_end,
                is_active=target_is_active,
                exclude_override_id=row.id,
            )

            updated = self.override_repo.update(row, auto_commit=False, **updates)
            self.db.commit()
            return updated
        except Exception:
            self.db.rollback()
            raise
