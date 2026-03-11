from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.service_location import ServiceLocation


class ServiceLocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> ServiceLocation:
        row = ServiceLocation(**kwargs)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_by_service_and_location(self, service_id: int, location_id: int) -> ServiceLocation | None:
        stmt = select(ServiceLocation).where(
            ServiceLocation.service_id == service_id,
            ServiceLocation.location_id == location_id,
        )
        return self.db.scalar(stmt)

    def list_by_service(self, service_id: int, *, include_inactive_locations: bool = False) -> list[ServiceLocation]:
        stmt = (
            select(ServiceLocation)
            .options(joinedload(ServiceLocation.location))
            .where(ServiceLocation.service_id == service_id)
            .order_by(ServiceLocation.id.asc())
        )
        if not include_inactive_locations:
            stmt = stmt.where(ServiceLocation.location.has(is_active=True))
        return list(self.db.scalars(stmt))

    def delete(self, row: ServiceLocation) -> None:
        self.db.delete(row)
        self.db.commit()
