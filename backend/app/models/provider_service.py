from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProviderService(Base, TimestampMixin):
    __tablename__ = "provider_services"
    __table_args__ = (
        UniqueConstraint("provider_id", "service_id", name="uq_provider_services_provider_service"),
        CheckConstraint(
            "duration_minutes_override IS NULL OR duration_minutes_override > 0",
            name="ck_provider_services_positive_duration_override",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    duration_minutes_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    provider = relationship("Provider", back_populates="provider_services")
    service = relationship("Service", back_populates="provider_services")
