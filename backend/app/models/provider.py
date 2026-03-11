from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Provider(Base, TimestampMixin):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("appointment_duration_minutes > 0", name="ck_providers_positive_duration"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        unique=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    appointment_duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    organization = relationship("Organization", back_populates="providers")
    user = relationship("User", back_populates="provider_profile")
    availabilities = relationship("ProviderAvailability", back_populates="provider", cascade="all, delete-orphan")
    date_overrides = relationship("ProviderDateOverride", back_populates="provider", cascade="all, delete-orphan")
    time_off_intervals = relationship("ProviderTimeOff", back_populates="provider", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="provider")
    provider_services = relationship("ProviderService", back_populates="provider", cascade="all, delete-orphan")
    provider_locations = relationship("ProviderLocation", back_populates="provider", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="provider")
