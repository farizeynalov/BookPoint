from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Organization:
        organization = Organization(**kwargs)
        self.db.add(organization)
        self.db.commit()
        self.db.refresh(organization)
        return organization

    def get(self, organization_id: int) -> Organization | None:
        return self.db.get(Organization, organization_id)

    def list_all(self) -> list[Organization]:
        stmt = select(Organization).order_by(Organization.id.asc())
        return list(self.db.scalars(stmt))

    def update(self, organization: Organization, **kwargs) -> Organization:
        for field, value in kwargs.items():
            setattr(organization, field, value)
        self.db.add(organization)
        self.db.commit()
        self.db.refresh(organization)
        return organization
