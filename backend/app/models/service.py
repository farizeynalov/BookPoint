from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import PaymentType


class Service(Base, TimestampMixin):
    __tablename__ = "services"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_services_positive_duration"),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_services_non_negative_price"),
        CheckConstraint("buffer_before_minutes >= 0", name="ck_services_non_negative_buffer_before"),
        CheckConstraint("buffer_after_minutes >= 0", name="ck_services_non_negative_buffer_after"),
        CheckConstraint(
            "deposit_amount_minor IS NULL OR deposit_amount_minor > 0",
            name="ck_services_positive_deposit_amount_minor",
        ),
        CheckConstraint(
            "(payment_type != 'deposit') OR deposit_amount_minor IS NOT NULL",
            name="ck_services_deposit_requires_amount",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    requires_payment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType, name="payment_type"),
        nullable=False,
        default=PaymentType.FULL,
    )
    deposit_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization = relationship("Organization", back_populates="services")
    provider = relationship("Provider", back_populates="services")
    provider_services = relationship("ProviderService", back_populates="service", cascade="all, delete-orphan")
    service_locations = relationship("ServiceLocation", back_populates="service", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="service")
