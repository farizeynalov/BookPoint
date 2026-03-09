from sqlalchemy.orm import Session

from app.repositories.provider_availability_repository import ProviderAvailabilityRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.provider_availability import ProviderAvailabilityCreate, ProviderAvailabilityUpdate


class ProviderAvailabilityService:
    def __init__(self, db: Session):
        self.db = db
        self.provider_repo = ProviderRepository(db)
        self.availability_repo = ProviderAvailabilityRepository(db)

    def create_availability(self, payload: ProviderAvailabilityCreate):
        try:
            provider = self.provider_repo.get_for_update(payload.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")
            if payload.start_time >= payload.end_time:
                raise ValueError("Availability start_time must be before end_time.")

            if payload.is_active and self.availability_repo.has_overlap(
                provider_id=payload.provider_id,
                weekday=payload.weekday,
                start_time=payload.start_time,
                end_time=payload.end_time,
            ):
                raise ValueError("Overlapping availability block exists for this provider and weekday.")

            block = self.availability_repo.create(auto_commit=False, **payload.model_dump())
            self.db.commit()
            return block
        except Exception:
            self.db.rollback()
            raise

    def update_availability(self, availability_id: int, payload: ProviderAvailabilityUpdate):
        try:
            availability = self.availability_repo.get(availability_id)
            if availability is None:
                raise ValueError("Availability block not found.")

            provider = self.provider_repo.get_for_update(availability.provider_id)
            if provider is None:
                raise ValueError("Provider not found.")

            updates = payload.model_dump(exclude_unset=True)
            target_weekday = updates.get("weekday", availability.weekday)
            target_start_time = updates.get("start_time", availability.start_time)
            target_end_time = updates.get("end_time", availability.end_time)
            target_is_active = updates.get("is_active", availability.is_active)
            if target_start_time >= target_end_time:
                raise ValueError("Availability start_time must be before end_time.")

            if target_is_active and self.availability_repo.has_overlap(
                provider_id=availability.provider_id,
                weekday=target_weekday,
                start_time=target_start_time,
                end_time=target_end_time,
                exclude_availability_id=availability.id,
            ):
                raise ValueError("Overlapping availability block exists for this provider and weekday.")

            updated = self.availability_repo.update(availability, auto_commit=False, **updates)
            self.db.commit()
            return updated
        except Exception:
            self.db.rollback()
            raise
