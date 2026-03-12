from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ProviderEarningStatus


class ProviderEarning(Base, TimestampMixin):
    __tablename__ = "provider_earnings"
    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_provider_earnings_payment_id"),
        CheckConstraint("gross_amount_minor >= 0", name="ck_provider_earnings_non_negative_gross"),
        CheckConstraint("platform_fee_minor >= 0", name="ck_provider_earnings_non_negative_platform_fee"),
        CheckConstraint("provider_amount_minor >= 0", name="ck_provider_earnings_non_negative_provider_amount"),
        CheckConstraint("refunded_amount_minor >= 0", name="ck_provider_earnings_non_negative_refunded_amount"),
        CheckConstraint("adjustment_pending_minor >= 0", name="ck_provider_earnings_non_negative_adjustment_pending"),
        CheckConstraint(
            "platform_fee_minor + provider_amount_minor <= gross_amount_minor",
            name="ck_provider_earnings_provider_plus_fee_lte_gross",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    payout_id: Mapped[int | None] = mapped_column(ForeignKey("payouts.id", ondelete="SET NULL"), nullable=True, index=True)
    gross_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_fee_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    refunded_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adjustment_pending_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[ProviderEarningStatus] = mapped_column(
        Enum(
            ProviderEarningStatus,
            name="provider_earning_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ProviderEarningStatus.PENDING,
        index=True,
    )

    provider = relationship("Provider", back_populates="earnings")
    appointment = relationship("Appointment", back_populates="earnings")
    payment = relationship("Payment", back_populates="provider_earning")
    payout = relationship("Payout", back_populates="earnings")
