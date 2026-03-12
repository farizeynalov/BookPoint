from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus, PaymentStatus, PaymentType
from app.models.payment import Payment
from app.services.payments.service import PaymentService
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
    requires_payment: bool = False,
    payment_type: str = "full",
    deposit_amount_minor: int | None = None,
    price: str = "25.00",
):
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
            "payment_type": payment_type,
            "deposit_amount_minor": deposit_amount_minor,
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


def _first_slot(
    client: TestClient,
    *,
    provider_id: int,
    service_id: int,
    location_id: int,
    query_date: date,
) -> str:
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
    return payload[0]["start_datetime"]


def _setup_context(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    name_suffix: str,
    requires_payment: bool,
    payment_type: str = "full",
    deposit_amount_minor: int | None = None,
    price: str = "25.00",
) -> dict:
    org = _create_org(client, auth_headers, name=f"Phase52 Org {name_suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Phase52 Provider {name_suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Phase52 Service {name_suffix}",
        requires_payment=requires_payment,
        payment_type=payment_type,
        deposit_amount_minor=deposit_amount_minor,
        price=price,
    )
    _add_availability(client, auth_headers, provider_id=provider["id"])
    monday = _next_weekday(0)
    slot_start = _first_slot(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=monday,
    )
    return {
        "organization_id": org["id"],
        "location_id": location_id,
        "provider_id": provider["id"],
        "service_id": service["id"],
        "slot_start": slot_start,
    }


def _book(client: TestClient, context: dict, *, suffix: str):
    return client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": context["organization_id"],
            "location_id": context["location_id"],
            "provider_id": context["provider_id"],
            "service_id": context["service_id"],
            "scheduled_start": context["slot_start"],
            "customer_name": f"Phase52 Customer {suffix}",
            "customer_phone": f"+1555800{suffix}",
            "customer_email": f"phase52-{suffix}@test.local",
            "preferred_language": "en",
        },
    )


def _confirm_payment(client: TestClient, *, checkout_session_id: str, status: str):
    return client.post(
        "/api/v1/payments/confirm",
        headers={"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key},
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": checkout_session_id,
            "status": status,
        },
    )


def test_paid_booking_sets_appointment_pending_payment(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, name_suffix="pending", requires_payment=True, price="30.00")
    booking = _book(client, context, suffix="60001")
    assert booking.status_code == 201, booking.text
    payload = booking.json()
    assert payload["status"] == AppointmentStatus.PENDING_PAYMENT.value


def test_deposit_service_uses_deposit_amount_in_payment_record(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(
        client,
        auth_headers,
        name_suffix="deposit-amount",
        requires_payment=True,
        payment_type="deposit",
        deposit_amount_minor=900,
        price="50.00",
    )
    booking = _book(client, context, suffix="60002")
    assert booking.status_code == 201, booking.text
    appointment_id = booking.json()["appointment_id"]
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == appointment_id))
    assert payment is not None
    assert payment.payment_type == PaymentType.DEPOSIT
    assert payment.amount_minor == 900


def test_payment_success_confirms_pending_payment_appointment(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, name_suffix="success", requires_payment=True, price="33.00")
    booking = _book(client, context, suffix="60003").json()
    confirm = _confirm_payment(
        client,
        checkout_session_id=booking["payment"]["checkout_session_id"],
        status="succeeded",
    )
    assert confirm.status_code == 200, confirm.text
    appointment = db_session.get(Appointment, booking["appointment_id"])
    assert appointment is not None
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_payment_failure_auto_cancels_pending_payment_appointment(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, name_suffix="failure", requires_payment=True, price="19.00")
    booking = _book(client, context, suffix="60004").json()
    confirm = _confirm_payment(
        client,
        checkout_session_id=booking["payment"]["checkout_session_id"],
        status="failed",
    )
    assert confirm.status_code == 200, confirm.text
    appointment = db_session.get(Appointment, booking["appointment_id"])
    assert appointment is not None
    assert appointment.status == AppointmentStatus.CANCELLED


def test_payment_timeout_job_cancels_pending_booking(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, name_suffix="timeout", requires_payment=True, price="21.00")
    booking = _book(client, context, suffix="60005").json()
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    payment.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    result = PaymentService(db_session).expire_pending_payments(
        expiration_minutes=15,
        now_utc=datetime.now(timezone.utc),
    )
    assert result["expired"] >= 1

    refreshed_payment = db_session.get(Payment, payment.id)
    appointment = db_session.get(Appointment, booking["appointment_id"])
    assert refreshed_payment is not None
    assert refreshed_payment.status == PaymentStatus.CANCELED
    assert appointment is not None
    assert appointment.status == AppointmentStatus.CANCELLED


def test_pending_payment_booking_blocks_same_slot(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, name_suffix="blocks", requires_payment=True, price="29.00")
    first = _book(client, context, suffix="60006")
    assert first.status_code == 201, first.text

    second = _book(client, context, suffix="60007")
    assert second.status_code == 400


def test_auto_canceled_pending_payment_releases_slot(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, name_suffix="release", requires_payment=True, price="31.00")
    first = _book(client, context, suffix="60008").json()
    failed = _confirm_payment(
        client,
        checkout_session_id=first["payment"]["checkout_session_id"],
        status="failed",
    )
    assert failed.status_code == 200, failed.text

    second = _book(client, context, suffix="60009")
    assert second.status_code == 201, second.text


def test_unpaid_booking_still_confirms_immediately(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, name_suffix="unpaid", requires_payment=False, price="24.00")
    booking = _book(client, context, suffix="60010")
    assert booking.status_code == 201, booking.text
    assert booking.json()["status"] == AppointmentStatus.CONFIRMED.value


def test_customer_retrieval_shows_pending_payment_summary(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, name_suffix="summary", requires_payment=True, price="34.00")
    booking = _book(client, context, suffix="60011").json()
    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == AppointmentStatus.PENDING_PAYMENT.value
    assert payload["payment"]["payment_required"] is True
    assert payload["payment"]["payment_status"] == PaymentStatus.REQUIRES_ACTION.value
    assert payload["payment"]["checkout_url"] is not None
    assert payload["payment"]["expires_at"] is not None


def test_payment_required_notification_hook_fires_on_paid_booking(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, name_suffix="notify-required", requires_payment=True, price="27.00")
    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.payments.service.enqueue_payment_required_notification",
        lambda appointment_id: captured.append(appointment_id),
    )
    booking = _book(client, context, suffix="60012")
    assert booking.status_code == 201, booking.text
    assert captured == [booking.json()["appointment_id"]]


def test_timeout_worker_task_triggers_timeout_notification(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, name_suffix="timeout-task", requires_payment=True, price="28.00")
    booking = _book(client, context, suffix="60013").json()
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    payment.created_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    db_session.add(payment)
    db_session.commit()
    db_session.refresh(payment)

    timeout_notifications: list[int] = []
    monkeypatch.setattr(
        "app.services.payments.service.enqueue_booking_auto_canceled_payment_timeout_notification",
        lambda appointment_id: timeout_notifications.append(appointment_id),
    )

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    result = worker_tasks.expire_pending_payments(expiration_minutes=15)
    assert result["expired"] >= 1
    assert timeout_notifications == [booking["appointment_id"]]


def test_existing_admin_provider_access_flow_still_passes(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Phase52 Existing Flow Org")
    _create_provider(client, auth_headers, organization_id=org["id"], name="Existing Flow Provider")

    with_auth = client.get("/api/v1/providers", headers=auth_headers)
    assert with_auth.status_code == 200

    without_auth = client.get("/api/v1/providers")
    assert without_auth.status_code == 401
