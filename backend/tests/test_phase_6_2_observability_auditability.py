from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.domain_event import DomainEvent
from app.models.enums import AppointmentStatus, BookingChannel
from app.models.organization import Organization
from app.models.organization_location import OrganizationLocation
from app.models.payment import Payment
from app.models.provider import Provider
from app.utils.phone import normalize_phone_number
from app.workers import tasks as worker_tasks


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


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


def _create_provider(client: TestClient, auth_headers: dict[str, str], *, organization_id: int, name: str) -> dict:
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "display_name": name,
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
    requires_payment: bool,
    price: str = "60.00",
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
            "price": price,
            "currency": "USD",
            "requires_payment": requires_payment,
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


def _add_availability(client: TestClient, auth_headers: dict[str, str], *, provider_id: int) -> None:
    response = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
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
) -> list[str]:
    response = client.get(
        f"/api/v1/discovery/providers/{provider_id}/slots",
        params={
            "service_id": service_id,
            "location_id": location_id,
            "date": query_date.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return [row["start_datetime"] for row in payload]


def _setup_context(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    suffix: str,
    requires_payment: bool,
) -> dict:
    org = _create_org(client, auth_headers, name=f"Phase62 Org {suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Provider {suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Service {suffix}",
        requires_payment=requires_payment,
    )
    _add_availability(client, auth_headers, provider_id=provider["id"])
    slots = _list_slots(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=_next_weekday(0),
    )
    return {
        "organization_id": org["id"],
        "location_id": location_id,
        "provider_id": provider["id"],
        "service_id": service["id"],
        "slots": slots,
    }


def _book(
    client: TestClient,
    *,
    context: dict,
    scheduled_start: str,
    suffix: str,
    idempotency_key: str | None = None,
):
    headers = {}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return client.post(
        "/api/v1/discovery/bookings",
        headers=headers,
        json={
            "organization_id": context["organization_id"],
            "location_id": context["location_id"],
            "provider_id": context["provider_id"],
            "service_id": context["service_id"],
            "scheduled_start": scheduled_start,
            "customer_name": f"Phase62 Customer {suffix}",
            "customer_phone": f"+1555200{suffix}",
            "customer_email": f"phase62-{suffix}@test.local",
            "preferred_language": "en",
        },
    )


def _confirm_payment(client: TestClient, *, checkout_session_id: str):
    return client.post(
        "/api/v1/payments/confirm",
        headers={"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key},
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": checkout_session_id,
            "status": "succeeded",
        },
    )


def _parse_metrics(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, value = stripped.split(" ", 1)
        metrics[name] = float(value)
    return metrics


def _create_upcoming_appointment(db_session: Session, *, minutes_from_now: int) -> Appointment:
    token = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    phone = f"+1777{token % 10_000_000:07d}"
    organization = Organization(
        name=f"Phase62 Notif Org {token}",
        slug=f"phase62-notif-org-{token}",
        business_type="clinic",
        city="Baku",
        address="Main",
        timezone="Asia/Baku",
        is_active=True,
    )
    provider = Provider(
        organization=organization,
        display_name=f"Phase62 Notif Provider {token}",
        appointment_duration_minutes=30,
        is_active=True,
    )
    location = OrganizationLocation(
        organization=organization,
        name="Main Location",
        slug=f"phase62-main-location-{token}",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    customer = Customer(
        full_name=f"Phase62 Notif Customer {token}",
        phone_number=phone,
        phone_number_normalized=normalize_phone_number(phone),
        email=f"phase62-notif-{token}@test.local",
        preferred_language="en",
    )
    start_datetime = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    appointment = Appointment(
        organization=organization,
        location=location,
        provider=provider,
        customer=customer,
        start_datetime=start_datetime,
        end_datetime=start_datetime + timedelta(minutes=30),
        status=AppointmentStatus.CONFIRMED,
        booking_channel=BookingChannel.WEB,
        notes="phase62-reminder",
    )
    db_session.add(appointment)
    db_session.commit()
    db_session.refresh(appointment)
    return appointment


def test_booking_creation_records_domain_event(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="booking-event", requires_payment=False)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92001")
    assert booking.status_code == 201, booking.text
    appointment_id = booking.json()["appointment_id"]

    event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "booking_created",
            DomainEvent.entity_type == "appointment",
            DomainEvent.entity_id == appointment_id,
        )
    )
    assert event is not None
    assert event.status == "success"
    assert event.organization_id == context["organization_id"]


def test_payment_success_records_domain_event(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="payment-event", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92002").json()
    confirm = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirm.status_code == 200, confirm.text

    payment_id = confirm.json()["payment_id"]
    event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "payment_confirmed",
            DomainEvent.related_payment_id == payment_id,
        )
    )
    assert event is not None
    assert event.status == "success"


def test_refund_success_records_domain_event(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="refund-event", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92003").json()
    confirm = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirm.status_code == 200, confirm.text
    payment_id = confirm.json()["payment_id"]

    refund = client.post(
        f"/api/v1/payments/{payment_id}/refund",
        headers=auth_headers,
        json={"amount_minor": 1000},
    )
    assert refund.status_code == 200, refund.text
    refund_id = refund.json()["id"]

    event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "refund_succeeded",
            DomainEvent.entity_type == "refund",
            DomainEvent.entity_id == refund_id,
        )
    )
    assert event is not None
    assert event.status == "success"


def test_payout_creation_and_completion_record_domain_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="payout-events", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92004").json()
    confirm = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirm.status_code == 200, confirm.text

    created = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert created.status_code == 201, created.text
    payout_id = created.json()["id"]

    created_event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "payout_created",
            DomainEvent.related_payout_id == payout_id,
        )
    )
    assert created_event is not None

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    result = worker_tasks.process_pending_payouts(provider_name="mock")
    assert result["completed"] >= 1

    completed_event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "payout_completed",
            DomainEvent.related_payout_id == payout_id,
        )
    )
    assert completed_event is not None
    assert completed_event.status == "success"


def test_metrics_endpoint_exposes_expected_counters_after_actions(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    context = _setup_context(client, auth_headers, suffix="metrics", requires_payment=True)
    first_booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92005").json()
    first_confirm = _confirm_payment(client, checkout_session_id=first_booking["payment"]["checkout_session_id"])
    assert first_confirm.status_code == 200, first_confirm.text
    first_payment_id = first_confirm.json()["payment_id"]

    refund = client.post(
        f"/api/v1/payments/{first_payment_id}/refund",
        headers=auth_headers,
        json={"amount_minor": 1000},
    )
    assert refund.status_code == 200, refund.text

    second_booking = _book(client, context=context, scheduled_start=context["slots"][1], suffix="920051").json()
    second_confirm = _confirm_payment(client, checkout_session_id=second_booking["payment"]["checkout_session_id"])
    assert second_confirm.status_code == 200, second_confirm.text

    payout = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert payout.status_code == 201, payout.text

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200, metrics_response.text
    metrics = _parse_metrics(metrics_response.text)

    assert metrics["bookings_created_total"] >= 1
    assert metrics["payments_required_total"] >= 1
    assert metrics["payments_succeeded_total"] >= 1
    assert metrics["refunds_succeeded_total"] >= 1
    assert metrics["payouts_created_total"] >= 1
    assert "idempotency_replays_total" in metrics


def test_idempotent_replay_increments_replay_metric(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, suffix="idem-metric", requires_payment=False)
    idem_key = "phase62-idem-key"
    first = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="92006",
        idempotency_key=idem_key,
    )
    second = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="92006",
        idempotency_key=idem_key,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200, metrics_response.text
    metrics = _parse_metrics(metrics_response.text)
    assert metrics["idempotency_replays_total"] >= 1


def test_admin_event_list_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/admin/events")
    assert response.status_code == 401


def test_admin_event_filtering_works(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, suffix="admin-filter", requires_payment=False)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92007")
    assert booking.status_code == 201, booking.text

    response = client.get(
        "/api/v1/admin/events",
        headers=auth_headers,
        params={
            "organization_id": context["organization_id"],
            "event_type": "booking_created",
            "status": "success",
            "limit": 50,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    assert all(row["event_type"] == "booking_created" for row in payload)
    assert all(row["organization_id"] == context["organization_id"] for row in payload)


def test_worker_driven_timeout_and_reminder_processing_records_events(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="worker-events", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92008").json()
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    payment.created_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    db_session.add(payment)
    db_session.commit()

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    timeout_result = worker_tasks.expire_pending_payments(expiration_minutes=15)
    assert timeout_result["expired"] >= 1

    timeout_event = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "booking_auto_canceled_payment_timeout",
            DomainEvent.related_appointment_id == booking["appointment_id"],
        )
    )
    assert timeout_event is not None
    assert timeout_event.request_id is not None
    assert timeout_event.request_id.startswith("wrk-")

    reminder_appointment = _create_upcoming_appointment(db_session, minutes_from_now=20)
    schedule_result = worker_tasks.schedule_upcoming_reminders(lookahead_minutes=60)
    assert schedule_result["queued"] >= 1
    reminder_result = worker_tasks.notify_appointment_reminder(reminder_appointment.id)
    assert reminder_result["status"] == "sent"

    reminder_scheduled = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "reminder_scheduled",
            DomainEvent.related_appointment_id == reminder_appointment.id,
        )
    )
    reminder_sent = db_session.scalar(
        select(DomainEvent).where(
            DomainEvent.event_type == "reminder_sent",
            DomainEvent.related_appointment_id == reminder_appointment.id,
        )
    )
    assert reminder_scheduled is not None
    assert reminder_sent is not None
    assert reminder_sent.request_id is not None


def test_existing_full_flows_still_pass(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="compat", requires_payment=False)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="92009")
    assert booking.status_code == 201, booking.text
    booking_payload = booking.json()

    customer_get = client.get(
        f"/api/v1/customer/bookings/{booking_payload['appointment_id']}",
        headers={"X-Booking-Token": booking_payload["booking_access_token"]},
    )
    assert customer_get.status_code == 200, customer_get.text

    cancel = client.post(
        f"/api/v1/customer/bookings/{booking_payload['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking_payload["booking_access_token"]},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == AppointmentStatus.CANCELLED.value

    all_events = list(db_session.scalars(select(DomainEvent)))
    assert all_events
