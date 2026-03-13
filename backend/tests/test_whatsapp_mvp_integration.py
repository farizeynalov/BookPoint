from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.conversation_state import ConversationState
from app.models.customer import Customer
from app.models.enums import AppointmentStatus, BookingChannel, ChannelType, MessageDirection
from app.models.message_log import MessageLog
from app.schemas.whatsapp import WhatsAppGatewaySendResult
from app.services.whatsapp.parser import normalize_whatsapp_messages
from app.utils.phone import normalize_phone_number


def _build_webhook_text_payload(*, from_user: str, message_id: str, text: str) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "123456",
                            },
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": from_user}],
                            "messages": [
                                {
                                    "from": from_user,
                                    "id": message_id,
                                    "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _build_webhook_action_payload(
    *,
    from_user: str,
    message_id: str,
    action_id: str,
    action_title: str = "Option",
    interactive_type: str = "button_reply",
) -> dict[str, Any]:
    action_key = "button_reply" if interactive_type == "button_reply" else "list_reply"
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550000000",
                                "phone_number_id": "123456",
                            },
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": from_user}],
                            "messages": [
                                {
                                    "from": from_user,
                                    "id": message_id,
                                    "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                                    "type": "interactive",
                                    "interactive": {
                                        "type": interactive_type,
                                        action_key: {
                                            "id": action_id,
                                            "title": action_title,
                                        },
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _send_whatsapp_text(client: TestClient, *, from_user: str, message_id: str, text: str):
    payload = _build_webhook_text_payload(from_user=from_user, message_id=message_id, text=text)
    return client.post("/api/v1/whatsapp/webhook", json=payload)


def _send_whatsapp_action(
    client: TestClient,
    *,
    from_user: str,
    message_id: str,
    action_id: str,
    action_title: str = "Option",
    interactive_type: str = "button_reply",
):
    payload = _build_webhook_action_payload(
        from_user=from_user,
        message_id=message_id,
        action_id=action_id,
        action_title=action_title,
        interactive_type=interactive_type,
    )
    return client.post("/api/v1/whatsapp/webhook", json=payload)


def _create_org(client: TestClient, auth_headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": name,
            "business_type": "clinic",
            "city": "Baku",
            "address": "Main",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _get_default_location_id(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.get(f"/api/v1/organizations/{organization_id}/locations", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["id"]


def _create_provider(client: TestClient, auth_headers: dict[str, str], *, organization_id: int, display_name: str) -> dict:
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "display_name": display_name,
            "appointment_duration_minutes": 30,
            "is_active": True,
            "user_id": None,
            "title": None,
            "bio": None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_service(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    organization_id: int,
    provider_id: int,
    name: str,
) -> dict:
    response = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": name,
            "description": None,
            "duration_minutes": 30,
            "price": "25.00",
            "currency": "USD",
            "requires_payment": False,
            "payment_type": "full",
            "deposit_amount_minor": None,
            "cancellation_policy_type": "flexible",
            "cancellation_window_hours": 24,
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_availability(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    weekday: int,
) -> None:
    response = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": weekday,
            "start_time": "09:00:00",
            "end_time": "12:00:00",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text


def _list_slots(
    client: TestClient,
    *,
    provider_id: int,
    service_id: int,
    location_id: int,
    query_date: date,
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/v1/discovery/providers/{provider_id}/slots",
        params={
            "service_id": service_id,
            "location_id": location_id,
            "date": query_date.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _slot_timestamp(slot_iso: str) -> int:
    return int(datetime.fromisoformat(slot_iso.replace("Z", "+00:00")).timestamp())


@pytest.fixture
def whatsapp_gateway_capture(monkeypatch):
    sent: list[dict[str, Any]] = []
    counter = {"value": 0}

    def _next_id() -> str:
        counter["value"] += 1
        return f"wamid.outbound.{counter['value']}"

    def _send_text(self, *, to: str, body: str):
        msg_id = _next_id()
        sent.append({"type": "text", "to": to, "body": body})
        return WhatsAppGatewaySendResult(
            external_message_id=msg_id,
            provider_payload={"messages": [{"id": msg_id}]},
        )

    def _send_buttons(self, *, to: str, body: str, buttons):
        msg_id = _next_id()
        sent.append(
            {
                "type": "buttons",
                "to": to,
                "body": body,
                "buttons": [button.model_dump(mode="json") for button in buttons],
            }
        )
        return WhatsAppGatewaySendResult(
            external_message_id=msg_id,
            provider_payload={"messages": [{"id": msg_id}]},
        )

    def _send_list(self, *, to: str, body: str, list_button_text: str, sections, header_text=None, footer_text=None):
        msg_id = _next_id()
        sent.append(
            {
                "type": "list",
                "to": to,
                "body": body,
                "button": list_button_text,
                "sections": [section.model_dump(mode="json") for section in sections],
                "header_text": header_text,
                "footer_text": footer_text,
            }
        )
        return WhatsAppGatewaySendResult(
            external_message_id=msg_id,
            provider_payload={"messages": [{"id": msg_id}]},
        )

    monkeypatch.setattr("app.services.whatsapp.service.WhatsAppCloudApiGateway.send_text", _send_text)
    monkeypatch.setattr("app.services.whatsapp.service.WhatsAppCloudApiGateway.send_buttons", _send_buttons)
    monkeypatch.setattr("app.services.whatsapp.service.WhatsAppCloudApiGateway.send_list", _send_list)
    return sent


def test_whatsapp_webhook_verification_success_and_failure(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr("app.api.routers.whatsapp.settings.whatsapp_verify_token", "wa-verify-token")
    success = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wa-verify-token",
            "hub.challenge": "abc123",
        },
    )
    assert success.status_code == 200
    assert success.text == "abc123"

    failed = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "bad-token",
            "hub.challenge": "abc123",
        },
    )
    assert failed.status_code == 403


def test_whatsapp_webhook_signature_validation(client: TestClient, monkeypatch, whatsapp_gateway_capture) -> None:
    monkeypatch.setattr("app.api.routers.whatsapp.settings.whatsapp_app_secret", "super-secret")
    payload = _build_webhook_text_payload(from_user="+15550020009", message_id="wa-sig-1", text="hi")
    raw_payload = json.dumps(payload)

    missing_signature = client.post(
        "/api/v1/whatsapp/webhook",
        content=raw_payload,
        headers={"Content-Type": "application/json"},
    )
    assert missing_signature.status_code == 401

    signature = hmac.new(b"super-secret", raw_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    valid = client.post(
        "/api/v1/whatsapp/webhook",
        content=raw_payload,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    assert valid.status_code == 200, valid.text


def test_whatsapp_payload_parser_handles_text_button_and_list_reply() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"wa_id": "1555001", "profile": {"name": "Alice"}}],
                            "messages": [
                                {
                                    "from": "1555001",
                                    "id": "m1",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "menu"},
                                },
                                {
                                    "from": "1555001",
                                    "id": "m2",
                                    "timestamp": "1710000001",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {"id": "menu:book", "title": "Book"},
                                    },
                                },
                                {
                                    "from": "1555001",
                                    "id": "m3",
                                    "timestamp": "1710000002",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "list_reply",
                                        "list_reply": {"id": "org:1", "title": "Org 1"},
                                    },
                                },
                            ],
                        }
                    }
                ]
            }
        ]
    }
    messages = normalize_whatsapp_messages(payload)
    assert [message.message_type for message in messages] == ["text", "button_reply", "list_reply"]
    assert messages[0].text_body == "menu"
    assert messages[1].action_id == "menu:book"
    assert messages[2].action_id == "org:1"


def test_whatsapp_duplicate_webhook_message_is_ignored(
    client: TestClient,
    db_session: Session,
    whatsapp_gateway_capture,
) -> None:
    first = _send_whatsapp_text(
        client,
        from_user="+15550020001",
        message_id="wamid-inbound-dup-1",
        text="hi",
    )
    assert first.status_code == 200, first.text
    assert first.json()["processed_messages"] == 1
    sent_after_first = len(whatsapp_gateway_capture)
    assert sent_after_first >= 1

    second = _send_whatsapp_text(
        client,
        from_user="+15550020001",
        message_id="wamid-inbound-dup-1",
        text="hi",
    )
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["processed_messages"] == 0
    assert payload["duplicate_messages"] == 1
    assert len(whatsapp_gateway_capture) == sent_after_first

    inbound_logs = list(
        db_session.scalars(
            select(MessageLog).where(
                MessageLog.external_message_id == "wamid-inbound-dup-1",
                MessageLog.direction == MessageDirection.INBOUND,
                MessageLog.channel == ChannelType.WHATSAPP,
            )
        )
    )
    assert len(inbound_logs) == 1


def test_whatsapp_booking_flow_creates_appointment_and_updates_state(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    whatsapp_gateway_capture,
) -> None:
    organization = _create_org(client, auth_headers, name="WhatsApp Booking Org")
    location_id = _get_default_location_id(client, auth_headers, organization["id"])
    provider = _create_provider(
        client,
        auth_headers,
        organization_id=organization["id"],
        display_name="WhatsApp Provider",
    )
    service = _create_service(
        client,
        auth_headers,
        organization_id=organization["id"],
        provider_id=provider["id"],
        name="Consultation",
    )
    target_date = date.today() + timedelta(days=1)
    _add_availability(client, auth_headers, provider_id=provider["id"], weekday=target_date.weekday())
    slots = _list_slots(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=target_date,
    )
    assert len(slots) >= 1
    selected_slot_ts = _slot_timestamp(slots[0]["start_datetime"])

    from_user = "+15550030001"
    assert _send_whatsapp_text(client, from_user=from_user, message_id="wa-book-1", text="hi").status_code == 200
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-2",
            action_id=f"org:{organization['id']}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-3",
            action_id="menu:book",
            interactive_type="button_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-4",
            action_id=f"svc:{service['id']}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-5",
            action_id=f"prov:{provider['id']}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-6",
            action_id=f"date:{target_date.isoformat()}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-book-7",
            action_id=f"slot:{selected_slot_ts}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    confirmation = _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-book-8",
        action_id=f"confirm_book:yes:{selected_slot_ts}",
        interactive_type="button_reply",
    )
    assert confirmation.status_code == 200, confirmation.text

    customer = db_session.scalar(
        select(Customer).where(Customer.phone_number_normalized == normalize_phone_number(from_user))
    )
    assert customer is not None
    appointment = db_session.scalar(
        select(Appointment)
        .where(Appointment.customer_id == customer.id)
        .order_by(Appointment.id.desc())
    )
    assert appointment is not None
    assert appointment.booking_channel == BookingChannel.WHATSAPP
    assert appointment.status == AppointmentStatus.CONFIRMED

    conversation_state = db_session.scalar(
        select(ConversationState).where(
            ConversationState.customer_id == customer.id,
            ConversationState.channel == ChannelType.WHATSAPP,
        )
    )
    assert conversation_state is not None
    assert conversation_state.selected_organization_id == organization["id"]
    assert conversation_state.current_step == "select_action"
    assert len(whatsapp_gateway_capture) >= 8


def test_whatsapp_upcoming_and_cancel_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    whatsapp_gateway_capture,
) -> None:
    organization = _create_org(client, auth_headers, name="WhatsApp Cancel Org")
    location_id = _get_default_location_id(client, auth_headers, organization["id"])
    provider = _create_provider(
        client,
        auth_headers,
        organization_id=organization["id"],
        display_name="Cancel Provider",
    )
    service = _create_service(
        client,
        auth_headers,
        organization_id=organization["id"],
        provider_id=provider["id"],
        name="Cancel Service",
    )
    target_date = date.today() + timedelta(days=1)
    _add_availability(client, auth_headers, provider_id=provider["id"], weekday=target_date.weekday())
    slots = _list_slots(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=target_date,
    )
    assert slots

    from_user = "+15550030002"
    booking_response = client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization["id"],
            "location_id": location_id,
            "provider_id": provider["id"],
            "service_id": service["id"],
            "scheduled_start": slots[0]["start_datetime"],
            "customer_name": "WhatsApp Cancel",
            "customer_phone": from_user,
            "customer_email": "wa-cancel@test.local",
            "preferred_language": "en",
        },
    )
    assert booking_response.status_code == 201, booking_response.text
    appointment_id = booking_response.json()["appointment_id"]

    _send_whatsapp_text(client, from_user=from_user, message_id="wa-cancel-1", text="hi")
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-cancel-2",
        action_id=f"org:{organization['id']}",
        interactive_type="list_reply",
    )
    upcoming = _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-cancel-3",
        action_id="menu:upcoming",
        interactive_type="button_reply",
    )
    assert upcoming.status_code == 200, upcoming.text
    assert any(
        message["type"] == "list"
        and any(row["id"] == f"booking:{appointment_id}" for section in message["sections"] for row in section["rows"])
        for message in whatsapp_gateway_capture
    )

    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-cancel-4",
            action_id=f"booking:{appointment_id}",
            interactive_type="list_reply",
        ).status_code
        == 200
    )
    assert (
        _send_whatsapp_action(
            client,
            from_user=from_user,
            message_id="wa-cancel-5",
            action_id=f"booking_action:cancel:{appointment_id}",
            interactive_type="button_reply",
        ).status_code
        == 200
    )
    confirmed = _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-cancel-6",
        action_id=f"confirm_cancel:yes:{appointment_id}",
        interactive_type="button_reply",
    )
    assert confirmed.status_code == 200, confirmed.text

    updated = db_session.get(Appointment, appointment_id)
    assert updated is not None
    assert updated.status == AppointmentStatus.CANCELLED


def test_whatsapp_reschedule_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    whatsapp_gateway_capture,
) -> None:
    organization = _create_org(client, auth_headers, name="WhatsApp Reschedule Org")
    location_id = _get_default_location_id(client, auth_headers, organization["id"])
    provider = _create_provider(
        client,
        auth_headers,
        organization_id=organization["id"],
        display_name="Reschedule Provider",
    )
    service = _create_service(
        client,
        auth_headers,
        organization_id=organization["id"],
        provider_id=provider["id"],
        name="Reschedule Service",
    )
    target_date = date.today() + timedelta(days=1)
    _add_availability(client, auth_headers, provider_id=provider["id"], weekday=target_date.weekday())
    slots = _list_slots(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=target_date,
    )
    assert len(slots) >= 2

    from_user = "+15550030003"
    booking = client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization["id"],
            "location_id": location_id,
            "provider_id": provider["id"],
            "service_id": service["id"],
            "scheduled_start": slots[0]["start_datetime"],
            "customer_name": "WhatsApp Reschedule",
            "customer_phone": from_user,
            "customer_email": "wa-reschedule@test.local",
            "preferred_language": "en",
        },
    )
    assert booking.status_code == 201, booking.text
    appointment_id = booking.json()["appointment_id"]
    new_slot_ts = _slot_timestamp(slots[1]["start_datetime"])

    _send_whatsapp_text(client, from_user=from_user, message_id="wa-res-1", text="hi")
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-2",
        action_id=f"org:{organization['id']}",
        interactive_type="list_reply",
    )
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-3",
        action_id="menu:upcoming",
        interactive_type="button_reply",
    )
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-4",
        action_id=f"booking:{appointment_id}",
        interactive_type="list_reply",
    )
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-5",
        action_id=f"booking_action:reschedule:{appointment_id}",
        interactive_type="button_reply",
    )
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-6",
        action_id=f"resched_date:{appointment_id}:{target_date.isoformat()}",
        interactive_type="list_reply",
    )
    _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-7",
        action_id=f"resched_slot:{appointment_id}:{new_slot_ts}",
        interactive_type="list_reply",
    )
    confirmed = _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-res-8",
        action_id=f"confirm_reschedule:yes:{appointment_id}:{new_slot_ts}",
        interactive_type="button_reply",
    )
    assert confirmed.status_code == 200, confirmed.text

    updated = db_session.get(Appointment, appointment_id)
    assert updated is not None
    updated_start_utc = (
        updated.start_datetime.replace(tzinfo=timezone.utc)
        if updated.start_datetime.tzinfo is None
        else updated.start_datetime.astimezone(timezone.utc)
    )
    assert int(updated_start_utc.timestamp()) == new_slot_ts
    assert updated.status == AppointmentStatus.CONFIRMED


def test_whatsapp_invalid_interactive_payload_is_handled_safely(
    client: TestClient,
    whatsapp_gateway_capture,
) -> None:
    from_user = "+15550030004"
    first = _send_whatsapp_text(client, from_user=from_user, message_id="wa-invalid-1", text="hi")
    assert first.status_code == 200, first.text

    invalid = _send_whatsapp_action(
        client,
        from_user=from_user,
        message_id="wa-invalid-2",
        action_id="unknown:payload",
        interactive_type="button_reply",
    )
    assert invalid.status_code == 200, invalid.text
    assert invalid.json()["processed_messages"] == 1
    assert any(
        message["type"] == "text" and "no longer valid" in message["body"].lower()
        for message in whatsapp_gateway_capture
    )
