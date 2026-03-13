from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation_state import ConversationState
from app.models.enums import ChannelType


class ConversationStateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_customer_and_channel(self, *, customer_id: int, channel: ChannelType) -> ConversationState | None:
        stmt = select(ConversationState).where(
            ConversationState.customer_id == customer_id,
            ConversationState.channel == channel,
        )
        return self.db.scalar(stmt)

    def create(
        self,
        *,
        customer_id: int,
        channel: ChannelType,
        external_user_id: str | None = None,
        current_flow: str | None = None,
        current_step: str | None = None,
        selected_organization_id: int | None = None,
        selected_provider_id: int | None = None,
        selected_service_id: int | None = None,
        selected_location_id: int | None = None,
        selected_slot_start=None,
        context_json: dict | None = None,
        auto_commit: bool = True,
    ) -> ConversationState:
        state = ConversationState(
            customer_id=customer_id,
            channel=channel,
            external_user_id=external_user_id,
            current_flow=current_flow,
            current_step=current_step,
            selected_organization_id=selected_organization_id,
            selected_provider_id=selected_provider_id,
            selected_service_id=selected_service_id,
            selected_location_id=selected_location_id,
            selected_slot_start=selected_slot_start,
            context_json=context_json or {},
            last_interaction_at=datetime.now(timezone.utc),
        )
        self.db.add(state)
        self.db.flush()
        self.db.refresh(state)
        if auto_commit:
            self.db.commit()
        return state

    def update(self, state: ConversationState, *, auto_commit: bool = True, **kwargs) -> ConversationState:
        for field, value in kwargs.items():
            setattr(state, field, value)
        state.last_interaction_at = datetime.now(timezone.utc)
        self.db.add(state)
        self.db.flush()
        self.db.refresh(state)
        if auto_commit:
            self.db.commit()
        return state
