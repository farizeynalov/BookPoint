from sqlalchemy.orm import Session

from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_time_off_repository import ProviderTimeOffRepository
from app.schemas.provider_time_off import ProviderTimeOffCreate, ProviderTimeOffUpdate
from app.utils.datetime import ensure_aware_utc


class ProviderTimeOffService:
    def __init__(self, db: Session):
        self.db = db
        self.provider_repo = ProviderRepository(db)
        self.time_off_repo = ProviderTimeOffRepository(db)

    def _validate_datetimes(self, start_datetime, end_datetime) -> tuple:
        start = ensure_aware_utc(start_datetime)
        end = ensure_aware_utc(end_datetime)
        if start >= end:
            raise ValueError("Time-off start_datetime must be before end_datetime.")
        return start, end

    def create_time_off(self, payload: ProviderTimeOffCreate):
        try:
            provider = self.provider_repo.get_for_update(payload.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")
            start_datetime, end_datetime = self._validate_datetimes(payload.start_datetime, payload.end_datetime)
            row = self.time_off_repo.create(
                auto_commit=False,
                provider_id=payload.provider_id,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                reason=payload.reason,
            )
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise

    def update_time_off(self, time_off_id: int, payload: ProviderTimeOffUpdate):
        try:
            row = self.time_off_repo.get(time_off_id)
            if row is None:
                raise ValueError("Time-off interval not found.")
            provider = self.provider_repo.get_for_update(row.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")

            updates = payload.model_dump(exclude_unset=True)
            target_start = updates.get("start_datetime", row.start_datetime)
            target_end = updates.get("end_datetime", row.end_datetime)
            start_datetime, end_datetime = self._validate_datetimes(target_start, target_end)
            updates["start_datetime"] = start_datetime
            updates["end_datetime"] = end_datetime

            updated = self.time_off_repo.update(row, auto_commit=False, **updates)
            self.db.commit()
            return updated
        except Exception:
            self.db.rollback()
            raise
