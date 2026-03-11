from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider import Provider


class ProviderRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Provider:
        provider = Provider(**kwargs)
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        return provider

    def get(self, provider_id: int) -> Provider | None:
        return self.db.get(Provider, provider_id)

    def get_for_update(self, provider_id: int) -> Provider | None:
        stmt = select(Provider).where(Provider.id == provider_id).with_for_update()
        return self.db.scalar(stmt)

    def list_providers(self, organization_id: int | None = None) -> list[Provider]:
        stmt = select(Provider).order_by(Provider.id.asc())
        if organization_id is not None:
            stmt = stmt.where(Provider.organization_id == organization_id)
        return list(self.db.scalars(stmt))

    def update(self, provider: Provider, **kwargs) -> Provider:
        for field, value in kwargs.items():
            setattr(provider, field, value)
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        return provider
