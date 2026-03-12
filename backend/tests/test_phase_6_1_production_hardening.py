from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import health as health_module
from app.core.config import settings
from app.core.health import DependencyHealth
from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.enums import (
    AppointmentStatus,
    BookingChannel,
    NotificationType,
    PaymentStatus,
    PayoutStatus,
)
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.organization_location import OrganizationLocation
from app.models.payment import Payment
from app.models.payout import Payout
from app.models.provider import Provider
from app.models.provider_earning import ProviderEarning
from app.models.refund import Refund
from app.utils.phone import normalize_phone_number
from app.workers import tasks as worker_tasks


@pytest.fixture(autouse=True)
def _stub_notification_task_dispatch(monkeypatch):
    monkeypatch.setattr(
        "app.services.notifications.dispatcher.celery_app.send_task",
        lambda *args, **kwargs: None,
    )


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
    price: str = "50.00",
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
    price: str = "50.00",
) -> dict:
    org = _create_org(client, auth_headers, name=f"Phase61 Org {suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Provider {suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Service {suffix}",
        requires_payment=requires_payment,
        price=price,
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
            "customer_name": f"Phase61 Customer {suffix}",
            "customer_phone": f"+1555100{suffix}",
            "customer_email": f"phase61-{suffix}@test.local",
            "preferred_language": "en",
        },
    )


def _confirm_payment(
    client: TestClient,
    *,
    checkout_session_id: str,
    status_value: str = "succeeded",
    idempotency_key: str | None = None,
):
    headers = {"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return client.post(
        "/api/v1/payments/confirm",
        headers=headers,
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": checkout_session_id,
            "status": status_value,
        },
    )


def _create_upcoming_appointment(db_session: Session, *, minutes_from_now: int) -> Appointment:
    token = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    phone = f"+1888{token % 10_000_000:07d}"
    organization = Organization(
        name=f"Phase61 Notif Org {token}",
        slug=f"phase61-notif-org-{token}",
        business_type="clinic",
        city="Baku",
        address="Main",
        timezone="Asia/Baku",
        is_active=True,
    )
    provider = Provider(
        organization=organization,
        display_name=f"Phase61 Notif Provider {token}",
        appointment_duration_minutes=30,
        is_active=True,
    )
    location = OrganizationLocation(
        organization=organization,
        name="Main Location",
        slug=f"phase61-main-location-{token}",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    customer = Customer(
        full_name=f"Phase61 Notif Customer {token}",
        phone_number=phone,
        phone_number_normalized=normalize_phone_number(phone),
        email=f"phase61-notif-{token}@test.local",
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
        notes="phase61-reminder",
    )
    db_session.add(appointment)
    db_session.commit()
    db_session.refresh(appointment)
    return appointment


def test_request_id_middleware_propagates_and_preserves_header(client: TestClient) -> None:
    generated = client.get("/health")
    assert generated.status_code == 200, generated.text
    assert generated.headers.get("X-Request-ID")

    custom = client.get("/health", headers={"X-Request-ID": "phase61-request-1"})
    assert custom.status_code == 200, custom.text
    assert custom.headers.get("X-Request-ID") == "phase61-request-1"


def test_standardized_error_shape_includes_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/providers")
    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]
    assert payload["detail"] == payload["error"]["message"]


def test_health_ready_success_with_dependency_checks(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        health_module,
        "check_database_health",
        lambda: DependencyHealth(name="database", ok=True, latency_ms=1.5),
    )
    monkeypatch.setattr(
        health_module,
        "check_redis_health",
        lambda: DependencyHealth(name="redis", ok=True, latency_ms=1.1),
    )

    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"


def test_health_ready_fails_when_dependency_unavailable(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        health_module,
        "check_database_health",
        lambda: DependencyHealth(name="database", ok=True, latency_ms=1.3),
    )
    monkeypatch.setattr(
        health_module,
        "check_redis_health",
        lambda: DependencyHealth(name="redis", ok=False, latency_ms=2.2, error="ConnectionError"),
    )

    response = client.get("/health/ready")
    assert response.status_code == 503, response.text
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["redis"]["status"] == "error"


def test_idempotent_booking_creation_prevents_duplicates(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="idem-booking", requires_payment=False)
    idem_key = "phase61-booking-key"

    first = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="91001",
        idempotency_key=idem_key,
    )
    second = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="91001",
        idempotency_key=idem_key,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["appointment_id"] == second.json()["appointment_id"]

    appointments = list(db_session.scalars(select(Appointment)))
    assert len(appointments) == 1


def test_idempotent_payment_confirm_prevents_duplicate_side_effects(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="idem-confirm", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91002").json()
    checkout_session_id = booking["payment"]["checkout_session_id"]
    captured_notifications: list[int] = []
    monkeypatch.setattr(
        "app.services.payments.service.enqueue_payment_succeeded_notification",
        lambda appointment_id: captured_notifications.append(appointment_id),
    )

    first = _confirm_payment(
        client,
        checkout_session_id=checkout_session_id,
        idempotency_key="phase61-confirm-key",
    )
    second = _confirm_payment(
        client,
        checkout_session_id=checkout_session_id,
        idempotency_key="phase61-confirm-key",
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["payment_id"] == second.json()["payment_id"]
    assert captured_notifications == [booking["appointment_id"]]

    payment = db_session.get(Payment, first.json()["payment_id"])
    assert payment is not None
    assert payment.status == PaymentStatus.SUCCEEDED
    earnings = list(db_session.scalars(select(ProviderEarning).where(ProviderEarning.payment_id == payment.id)))
    assert len(earnings) == 1


def test_duplicate_payout_create_with_same_idempotency_key_does_not_duplicate_payout(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="idem-payout", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91003").json()
    confirmed = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirmed.status_code == 200, confirmed.text

    headers = {**auth_headers, "Idempotency-Key": "phase61-payout-key"}
    first = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=headers)
    second = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    payouts = list(db_session.scalars(select(Payout).where(Payout.provider_id == context["provider_id"])))
    assert len(payouts) == 1


def test_duplicate_manual_refund_with_same_idempotency_key_does_not_duplicate_refund(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="idem-refund", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91004").json()
    confirmed = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirmed.status_code == 200, confirmed.text
    payment = db_session.get(Payment, confirmed.json()["payment_id"])
    assert payment is not None

    headers = {**auth_headers, "Idempotency-Key": "phase61-refund-key"}
    first = client.post(f"/api/v1/payments/{payment.id}/refund", headers=headers, json={"amount_minor": 1000})
    second = client.post(f"/api/v1/payments/{payment.id}/refund", headers=headers, json={"amount_minor": 1000})
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    refunds = list(db_session.scalars(select(Refund).where(Refund.payment_id == payment.id)))
    assert len(refunds) == 1


def test_expiration_worker_safe_on_repeated_invocation(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="worker-expire", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91005").json()
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    payment.created_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    db_session.add(payment)
    db_session.commit()

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    first = worker_tasks.expire_pending_payments(expiration_minutes=15)
    second = worker_tasks.expire_pending_payments(expiration_minutes=15)
    assert first["expired"] >= 1
    assert second["expired"] == 0


def test_reminder_scheduler_safe_on_repeated_invocation(db_session: Session, monkeypatch) -> None:
    appointment = _create_upcoming_appointment(db_session, minutes_from_now=20)
    queued_ids: list[int] = []

    def fake_send_task(task_name: str, args=None, kwargs=None):
        if task_name == worker_tasks.REMINDER_TASK_NAME and args:
            queued_ids.append(args[0])
        return None

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(worker_tasks.celery_app, "send_task", fake_send_task)

    first = worker_tasks.schedule_upcoming_reminders(lookahead_minutes=60)
    second = worker_tasks.schedule_upcoming_reminders(lookahead_minutes=60)
    assert first["queued"] == 1
    assert second["queued"] == 0
    assert queued_ids == [appointment.id]

    notifications = list(
        db_session.scalars(
            select(Notification).where(
                Notification.appointment_id == appointment.id,
                Notification.type == NotificationType.REMINDER,
            )
        )
    )
    assert len(notifications) == 1


def test_payout_worker_safe_on_repeated_invocation(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="worker-payout", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91006").json()
    confirmed = _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    assert confirmed.status_code == 200, confirmed.text

    payout_response = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert payout_response.status_code == 201, payout_response.text
    payout_id = payout_response.json()["id"]

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    first = worker_tasks.process_pending_payouts(provider_name="mock")
    second = worker_tasks.process_pending_payouts(provider_name="mock")
    assert first["completed"] >= 1
    assert second["completed"] == 0

    payout = db_session.get(Payout, payout_id)
    assert payout is not None
    assert payout.status == PayoutStatus.COMPLETED


def test_full_booking_payment_refund_payout_flow_still_passes(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="flow-smoke", requires_payment=True, price="80.00")
    first_booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="91007").json()
    second_booking = _book(client, context=context, scheduled_start=context["slots"][1], suffix="91008").json()

    first_confirm = _confirm_payment(client, checkout_session_id=first_booking["payment"]["checkout_session_id"])
    second_confirm = _confirm_payment(client, checkout_session_id=second_booking["payment"]["checkout_session_id"])
    assert first_confirm.status_code == 200, first_confirm.text
    assert second_confirm.status_code == 200, second_confirm.text

    cancel = client.post(
        f"/api/v1/appointments/{first_booking['appointment_id']}/cancel",
        headers=auth_headers,
        json={"notes": "phase61-smoke-cancel"},
    )
    assert cancel.status_code == 200, cancel.text

    first_payment = db_session.get(Payment, first_confirm.json()["payment_id"])
    second_payment = db_session.get(Payment, second_confirm.json()["payment_id"])
    assert first_payment is not None
    assert second_payment is not None
    first_refunds = list(db_session.scalars(select(Refund).where(Refund.payment_id == first_payment.id)))
    assert first_refunds

    payout_create = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert payout_create.status_code == 201, payout_create.text
    payout_id = payout_create.json()["id"]

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    worker_result = worker_tasks.process_pending_payouts(provider_name="mock")
    assert worker_result["completed"] >= 1

    payout = db_session.get(Payout, payout_id)
    assert payout is not None
    assert payout.status == PayoutStatus.COMPLETED
