from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ChannelType, MessageDirection
from app.models.message_log import MessageLog


class MessageLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> MessageLog:
        row = MessageLog(**kwargs)
        self.db.add(row)
        self.db.flush()
        self.db.refresh(row)
        if auto_commit:
            self.db.commit()
        return row

    def get_by_channel_direction_external_message_id(
        self,
        *,
        channel: ChannelType,
        direction: MessageDirection,
        external_message_id: str,
    ) -> MessageLog | None:
        stmt = select(MessageLog).where(
            MessageLog.channel == channel,
            MessageLog.direction == direction,
            MessageLog.external_message_id == external_message_id,
        )
        return self.db.scalar(stmt)
