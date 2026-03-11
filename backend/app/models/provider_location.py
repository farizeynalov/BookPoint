from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProviderLocation(Base, TimestampMixin):
    __tablename__ = "provider_locations"
    __table_args__ = (
        UniqueConstraint("provider_id", "location_id", name="uq_provider_locations_provider_location"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("organization_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider = relationship("Provider", back_populates="provider_locations")
    location = relationship("OrganizationLocation", back_populates="provider_locations")
