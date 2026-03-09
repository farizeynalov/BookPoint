from sqlalchemy import Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ChannelType


class CustomerChannelIdentity(Base, TimestampMixin):
    __tablename__ = "customer_channel_identities"
    __table_args__ = (
        UniqueConstraint("customer_id", "channel", name="uq_customer_identity_customer_channel"),
        UniqueConstraint("channel", "external_user_id", name="uq_customer_identity_channel_external_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="channel_type"), nullable=False)
    external_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer = relationship("Customer", back_populates="channel_identities")
