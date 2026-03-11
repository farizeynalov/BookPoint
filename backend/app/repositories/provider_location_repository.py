from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.provider_location import ProviderLocation


class ProviderLocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> ProviderLocation:
        row = ProviderLocation(**kwargs)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_by_provider_and_location(self, provider_id: int, location_id: int) -> ProviderLocation | None:
        stmt = select(ProviderLocation).where(
            ProviderLocation.provider_id == provider_id,
            ProviderLocation.location_id == location_id,
        )
        return self.db.scalar(stmt)

    def list_by_provider(self, provider_id: int, *, include_inactive_locations: bool = False) -> list[ProviderLocation]:
        stmt = (
            select(ProviderLocation)
            .options(joinedload(ProviderLocation.location))
            .where(ProviderLocation.provider_id == provider_id)
            .order_by(ProviderLocation.id.asc())
        )
        if not include_inactive_locations:
            stmt = stmt.where(ProviderLocation.location.has(is_active=True))
        return list(self.db.scalars(stmt))

    def delete(self, row: ProviderLocation) -> None:
        self.db.delete(row)
        self.db.commit()
