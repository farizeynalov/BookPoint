from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization_location import OrganizationLocation
from app.utils.slug import slugify


class OrganizationLocationRepository:
    def __init__(self, db: Session):
        self.db = db

    def generate_unique_slug(
        self,
        *,
        organization_id: int,
        source: str,
        exclude_location_id: int | None = None,
    ) -> str:
        base_slug = slugify(source)
        candidate = base_slug
        suffix = 2
        while self._slug_exists(
            organization_id=organization_id,
            slug=candidate,
            exclude_location_id=exclude_location_id,
        ):
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        return candidate

    def _slug_exists(
        self,
        *,
        organization_id: int,
        slug: str,
        exclude_location_id: int | None = None,
    ) -> bool:
        stmt = select(OrganizationLocation.id).where(
            OrganizationLocation.organization_id == organization_id,
            OrganizationLocation.slug == slug,
        )
        if exclude_location_id is not None:
            stmt = stmt.where(OrganizationLocation.id != exclude_location_id)
        return self.db.scalar(stmt) is not None

    def create(self, **kwargs) -> OrganizationLocation:
        slug_source = kwargs.get("slug") or kwargs["name"]
        kwargs["slug"] = self.generate_unique_slug(
            organization_id=kwargs["organization_id"],
            source=slug_source,
        )
        row = OrganizationLocation(**kwargs)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, location_id: int) -> OrganizationLocation | None:
        return self.db.get(OrganizationLocation, location_id)

    def get_by_org_and_id(self, organization_id: int, location_id: int) -> OrganizationLocation | None:
        stmt = select(OrganizationLocation).where(
            OrganizationLocation.id == location_id,
            OrganizationLocation.organization_id == organization_id,
        )
        return self.db.scalar(stmt)

    def list_by_organization(self, organization_id: int, *, include_inactive: bool = True) -> list[OrganizationLocation]:
        stmt = (
            select(OrganizationLocation)
            .where(OrganizationLocation.organization_id == organization_id)
            .order_by(OrganizationLocation.id.asc())
        )
        if not include_inactive:
            stmt = stmt.where(OrganizationLocation.is_active.is_(True))
        return list(self.db.scalars(stmt))

    def update(self, location: OrganizationLocation, **kwargs) -> OrganizationLocation:
        if "slug" in kwargs and kwargs["slug"] is None:
            kwargs.pop("slug")
        if "slug" in kwargs and kwargs["slug"] is not None:
            kwargs["slug"] = self.generate_unique_slug(
                organization_id=location.organization_id,
                source=kwargs["slug"],
                exclude_location_id=location.id,
            )
        for field, value in kwargs.items():
            setattr(location, field, value)
        self.db.add(location)
        self.db.commit()
        self.db.refresh(location)
        return location
