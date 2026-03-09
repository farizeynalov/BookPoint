from app.models.enums import ChannelType
from app.schemas.common import ORMModel, TimestampRead


class CustomerChannelIdentityCreate(ORMModel):
    customer_id: int
    channel: ChannelType
    external_user_id: str
    external_chat_id: str | None = None


class CustomerChannelIdentityRead(TimestampRead):
    id: int
    customer_id: int
    channel: ChannelType
    external_user_id: str
    external_chat_id: str | None
