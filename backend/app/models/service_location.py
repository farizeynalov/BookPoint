from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ServiceLocation(Base, TimestampMixin):
    __tablename__ = "service_locations"
    __table_args__ = (
        UniqueConstraint("service_id", "location_id", name="uq_service_locations_service_location"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("organization_locations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    service = relationship("Service", back_populates="service_locations")
    location = relationship("OrganizationLocation", back_populates="service_locations")
