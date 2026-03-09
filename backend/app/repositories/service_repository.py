from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service import Service


class ServiceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Service:
        service = Service(**kwargs)
        self.db.add(service)
        self.db.commit()
        self.db.refresh(service)
        return service

    def get(self, service_id: int) -> Service | None:
        return self.db.get(Service, service_id)

    def list(self, organization_id: int | None = None, provider_id: int | None = None) -> list[Service]:
        stmt = select(Service).order_by(Service.id.asc())
        if organization_id is not None:
            stmt = stmt.where(Service.organization_id == organization_id)
        if provider_id is not None:
            stmt = stmt.where(Service.provider_id == provider_id)
        return list(self.db.scalars(stmt))

    def update(self, service: Service, **kwargs) -> Service:
        for field, value in kwargs.items():
            setattr(service, field, value)
        self.db.add(service)
        self.db.commit()
        self.db.refresh(service)
        return service
