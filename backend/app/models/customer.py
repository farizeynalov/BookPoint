from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    phone_number_normalized: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    preferred_language: Mapped[str | None] = mapped_column(String(16), nullable=True)

    channel_identities = relationship("CustomerChannelIdentity", back_populates="customer", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="customer")
    conversation_states = relationship("ConversationState", back_populates="customer", cascade="all, delete-orphan")
