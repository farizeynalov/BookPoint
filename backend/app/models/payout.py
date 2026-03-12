from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import PayoutStatus


class Payout(Base, TimestampMixin):
    __tablename__ = "payouts"
    __table_args__ = (
        CheckConstraint("total_amount_minor >= 0", name="ck_payouts_non_negative_total_amount_minor"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True)
    total_amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PayoutStatus] = mapped_column(
        Enum(
            PayoutStatus,
            name="payout_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PayoutStatus.PENDING,
        index=True,
    )
    provider_payout_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider = relationship("Provider", back_populates="payouts")
    earnings = relationship("ProviderEarning", back_populates="payout")
