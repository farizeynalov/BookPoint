from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.models.enums import ChannelType
from app.schemas.common import ORMModel


class WhatsAppInboundMessage(ORMModel):
    channel: ChannelType = ChannelType.WHATSAPP
    external_message_id: str
    external_user_id: str
    external_chat_id: str | None = None
    message_type: Literal["text", "button_reply", "list_reply", "interactive_unknown", "unsupported"]
    text_body: str | None = None
    action_id: str | None = None
    action_title: str | None = None
    timestamp: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class WhatsAppListRow(ORMModel):
    id: str
    title: str
    description: str | None = None


class WhatsAppListSection(ORMModel):
    title: str
    rows: list[WhatsAppListRow]


class WhatsAppButtonOption(ORMModel):
    id: str
    title: str


class WhatsAppOutboundMessage(ORMModel):
    message_type: Literal["text", "buttons", "list"]
    body: str
    buttons: list[WhatsAppButtonOption] = Field(default_factory=list)
    list_button_text: str | None = None
    list_sections: list[WhatsAppListSection] = Field(default_factory=list)
    header_text: str | None = None
    footer_text: str | None = None

    @model_validator(mode="after")
    def _validate_message_shape(self):
        if self.message_type == "buttons":
            if not self.buttons:
                raise ValueError("buttons message requires at least one button.")
            if len(self.buttons) > 3:
                raise ValueError("buttons message supports at most three buttons.")
        if self.message_type == "list":
            if not self.list_button_text:
                raise ValueError("list message requires list_button_text.")
            if not self.list_sections:
                raise ValueError("list message requires at least one list section.")
        return self


class WhatsAppGatewaySendResult(ORMModel):
    external_message_id: str | None = None
    provider_payload: dict[str, Any] = Field(default_factory=dict)
