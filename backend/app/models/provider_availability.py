from datetime import time

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ProviderAvailability(Base, TimestampMixin):
    __tablename__ = "provider_availability"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_provider_availability_weekday_range"),
        CheckConstraint("start_time < end_time", name="ck_provider_availability_start_before_end"),
        UniqueConstraint(
            "provider_id",
            "weekday",
            "start_time",
            "end_time",
            name="uq_provider_availability_provider_weekday_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider = relationship("Provider", back_populates="availabilities")
