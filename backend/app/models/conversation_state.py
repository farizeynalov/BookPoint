from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ChannelType


class ConversationState(Base, TimestampMixin):
    __tablename__ = "conversation_states"
    __table_args__ = (UniqueConstraint("customer_id", "channel", name="uq_conversation_state_customer_channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel: Mapped[ChannelType] = mapped_column(Enum(ChannelType, name="conversation_channel_type"), nullable=False)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    current_flow: Mapped[str | None] = mapped_column(String(100), nullable=True)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    selected_organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("organization_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    selected_slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )

    customer = relationship("Customer", back_populates="conversation_states")
