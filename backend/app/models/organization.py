from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Enum, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.models.base import Base, TimestampMixin
from app.models.enums import CommissionType


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("commission_percentage >= 0 AND commission_percentage <= 1", name="ck_organizations_commission_percentage_range"),
        CheckConstraint("commission_fixed_minor >= 0", name="ck_organizations_commission_fixed_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    business_type: Mapped[str] = mapped_column(String(100), nullable=False, default="business")
    city: Mapped[str] = mapped_column(String(100), nullable=False, default=settings.default_city)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default=settings.default_timezone)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    commission_type: Mapped[CommissionType] = mapped_column(
        Enum(
            CommissionType,
            name="commission_type",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=CommissionType.PERCENTAGE,
    )
    commission_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.1000"))
    commission_fixed_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    members = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    locations = relationship("OrganizationLocation", back_populates="organization", cascade="all, delete-orphan")
    providers = relationship("Provider", back_populates="organization", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="organization", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="organization", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="organization", cascade="all, delete-orphan")
