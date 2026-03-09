from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ChannelType


class ConversationState(Base, TimestampMixin):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("customer_id", "channel", name="uq_conversation_state_customer_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="conversation_channel_type"), nullable=False)
    current_flow: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    customer = relationship("Customer", back_populates="conversation_states")
