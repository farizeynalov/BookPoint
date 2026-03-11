from datetime import date, time

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProviderDateOverride(Base, TimestampMixin):
    __tablename__ = "provider_date_overrides"
    __table_args__ = (
        CheckConstraint(
            "(is_available = true AND start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time) "
            "OR (is_available = false AND start_time IS NULL AND end_time IS NULL)",
            name="ck_provider_date_overrides_time_shape",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    override_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider = relationship("Provider", back_populates="date_overrides")
