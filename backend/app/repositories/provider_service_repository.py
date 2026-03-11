from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.provider_service import ProviderService


class ProviderServiceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> ProviderService:
        row = ProviderService(**kwargs)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, provider_service_id: int) -> ProviderService | None:
        return self.db.get(ProviderService, provider_service_id)

    def get_by_provider_and_service(self, provider_id: int, service_id: int) -> ProviderService | None:
        stmt = select(ProviderService).where(
            ProviderService.provider_id == provider_id,
            ProviderService.service_id == service_id,
        )
        return self.db.scalar(stmt)

    def list_by_provider(
        self,
        provider_id: int,
        *,
        include_inactive_services: bool = False,
    ) -> list[ProviderService]:
        stmt = (
            select(ProviderService)
            .options(joinedload(ProviderService.service))
            .where(ProviderService.provider_id == provider_id)
            .order_by(ProviderService.id.asc())
        )
        if not include_inactive_services:
            stmt = stmt.where(ProviderService.service.has(is_active=True))
        return list(self.db.scalars(stmt))

    def update(self, row: ProviderService, **kwargs) -> ProviderService:
        for field, value in kwargs.items():
            setattr(row, field, value)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, row: ProviderService) -> None:
        self.db.delete(row)
        self.db.commit()
