from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_channel_identity import CustomerChannelIdentity
from app.models.enums import ChannelType


class CustomerIdentityRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        customer_id: int,
        channel: ChannelType,
        external_user_id: str,
        external_chat_id: str | None = None,
    ) -> CustomerChannelIdentity:
        identity = CustomerChannelIdentity(
            customer_id=customer_id,
            channel=channel,
            external_user_id=external_user_id,
            external_chat_id=external_chat_id,
        )
        self.db.add(identity)
        self.db.commit()
        self.db.refresh(identity)
        return identity

    def list_by_customer(self, customer_id: int) -> list[CustomerChannelIdentity]:
        stmt = select(CustomerChannelIdentity).where(CustomerChannelIdentity.customer_id == customer_id)
        return list(self.db.scalars(stmt))

    def get_by_channel_external_user(self, channel: ChannelType, external_user_id: str) -> CustomerChannelIdentity | None:
        stmt = select(CustomerChannelIdentity).where(
            CustomerChannelIdentity.channel == channel,
            CustomerChannelIdentity.external_user_id == external_user_id,
        )
        return self.db.scalar(stmt)

    def get_by_customer_and_channel(self, customer_id: int, channel: ChannelType) -> CustomerChannelIdentity | None:
        stmt = select(CustomerChannelIdentity).where(
            CustomerChannelIdentity.customer_id == customer_id,
            CustomerChannelIdentity.channel == channel,
        )
        return self.db.scalar(stmt)
