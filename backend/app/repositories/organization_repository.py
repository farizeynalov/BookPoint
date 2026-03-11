from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.utils.slug import slugify


class OrganizationRepository:
    def __init__(self, db: Session):
        self.db = db

    def generate_unique_slug(self, source: str, *, exclude_organization_id: int | None = None) -> str:
        base_slug = slugify(source)
        candidate = base_slug
        suffix = 2
        while self._slug_exists(candidate, exclude_organization_id=exclude_organization_id):
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        return candidate

    def _slug_exists(self, slug: str, *, exclude_organization_id: int | None = None) -> bool:
        stmt = select(Organization.id).where(Organization.slug == slug)
        if exclude_organization_id is not None:
            stmt = stmt.where(Organization.id != exclude_organization_id)
        return self.db.scalar(stmt) is not None

    def create(self, **kwargs) -> Organization:
        slug_source = kwargs.get("slug") or kwargs["name"]
        kwargs["slug"] = self.generate_unique_slug(slug_source)
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
        if "slug" in kwargs and kwargs["slug"] is None:
            kwargs.pop("slug")
        if "slug" in kwargs and kwargs["slug"] is not None:
            kwargs["slug"] = self.generate_unique_slug(
                kwargs["slug"],
                exclude_organization_id=organization.id,
            )
        for field, value in kwargs.items():
            setattr(organization, field, value)
        self.db.add(organization)
        self.db.commit()
        self.db.refresh(organization)
        return organization

    def delete(self, organization: Organization) -> None:
        self.db.delete(organization)
        self.db.commit()
