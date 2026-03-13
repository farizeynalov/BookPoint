from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.whatsapp import WhatsAppInboundMessage


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    text = _as_str(value)
    if text is None:
        return None
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_whatsapp_messages(payload: dict[str, Any]) -> list[WhatsAppInboundMessage]:
    normalized: list[WhatsAppInboundMessage] = []
    for entry in payload.get("entry", []):
        entry_obj = _as_dict(entry)
        for change in entry_obj.get("changes", []):
            change_obj = _as_dict(change)
            value = _as_dict(change_obj.get("value"))
            contacts = value.get("contacts", [])
            wa_name_by_id: dict[str, str] = {}
            if isinstance(contacts, list):
                for contact in contacts:
                    contact_obj = _as_dict(contact)
                    wa_id = _as_str(contact_obj.get("wa_id"))
                    profile = _as_dict(contact_obj.get("profile"))
                    profile_name = _as_str(profile.get("name"))
                    if wa_id and profile_name:
                        wa_name_by_id[wa_id] = profile_name

            messages = value.get("messages", [])
            if not isinstance(messages, list):
                continue
            for message in messages:
                message_obj = _as_dict(message)
                external_message_id = _as_str(message_obj.get("id"))
                external_user_id = _as_str(message_obj.get("from"))
                if external_message_id is None or external_user_id is None:
                    continue

                message_type = _as_str(message_obj.get("type")) or "unsupported"
                timestamp = _parse_timestamp(message_obj.get("timestamp"))
                text_body: str | None = None
                action_id: str | None = None
                action_title: str | None = None
                normalized_type = "unsupported"

                if message_type == "text":
                    text_obj = _as_dict(message_obj.get("text"))
                    text_body = _as_str(text_obj.get("body"))
                    normalized_type = "text"
                elif message_type == "interactive":
                    interactive_obj = _as_dict(message_obj.get("interactive"))
                    interactive_type = _as_str(interactive_obj.get("type"))
                    if interactive_type == "button_reply":
                        button_obj = _as_dict(interactive_obj.get("button_reply"))
                        action_id = _as_str(button_obj.get("id"))
                        action_title = _as_str(button_obj.get("title"))
                        normalized_type = "button_reply"
                    elif interactive_type == "list_reply":
                        list_obj = _as_dict(interactive_obj.get("list_reply"))
                        action_id = _as_str(list_obj.get("id"))
                        action_title = _as_str(list_obj.get("title"))
                        normalized_type = "list_reply"
                    else:
                        normalized_type = "interactive_unknown"
                elif message_type == "button":
                    button_obj = _as_dict(message_obj.get("button"))
                    action_id = _as_str(button_obj.get("payload"))
                    action_title = _as_str(button_obj.get("text"))
                    normalized_type = "button_reply"

                normalized.append(
                    WhatsAppInboundMessage(
                        external_message_id=external_message_id,
                        external_user_id=external_user_id,
                        external_chat_id=wa_name_by_id.get(external_user_id),
                        message_type=normalized_type,
                        text_body=text_body,
                        action_id=action_id,
                        action_title=action_title,
                        timestamp=timestamp,
                        raw_payload=message_obj,
                    )
                )
    return normalized
