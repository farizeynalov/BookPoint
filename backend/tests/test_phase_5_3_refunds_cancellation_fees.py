from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus, PaymentStatus, PaymentType, RefundStatus
from app.models.payment import Payment
from app.models.refund import Refund


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
    payment_type: str = "full",
    deposit_amount_minor: int | None = None,
    price: str = "100.00",
    cancellation_policy_type: str = "flexible",
    cancellation_window_hours: int = 24,
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
            "payment_type": payment_type,
            "deposit_amount_minor": deposit_amount_minor,
            "cancellation_policy_type": cancellation_policy_type,
            "cancellation_window_hours": cancellation_window_hours,
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
    suffix: str,
    requires_payment: bool = True,
    payment_type: str = "full",
    deposit_amount_minor: int | None = None,
    price: str = "100.00",
    cancellation_policy_type: str = "flexible",
    cancellation_window_hours: int = 24,
) -> dict:
    org = _create_org(client, auth_headers, name=f"Phase53 Org {suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Phase53 Provider {suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Phase53 Service {suffix}",
        requires_payment=requires_payment,
        payment_type=payment_type,
        deposit_amount_minor=deposit_amount_minor,
        price=price,
        cancellation_policy_type=cancellation_policy_type,
        cancellation_window_hours=cancellation_window_hours,
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
    response = client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": context["organization_id"],
            "location_id": context["location_id"],
            "provider_id": context["provider_id"],
            "service_id": context["service_id"],
            "scheduled_start": context["slot_start"],
            "customer_name": f"Phase53 Customer {suffix}",
            "customer_phone": f"+1555900{suffix}",
            "customer_email": f"phase53-{suffix}@test.local",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_payment(client: TestClient, *, checkout_session_id: str) -> None:
    response = client.post(
        "/api/v1/payments/confirm",
        headers={"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key},
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": checkout_session_id,
            "status": "succeeded",
        },
    )
    assert response.status_code == 200, response.text


def _set_appointment_hours_before_start(
    db_session: Session,
    *,
    appointment_id: int,
    hours_before_start: int,
) -> None:
    appointment = db_session.get(Appointment, appointment_id)
    assert appointment is not None
    start = datetime.now(timezone.utc) + timedelta(hours=hours_before_start)
    appointment.start_datetime = start
    appointment.end_datetime = start + timedelta(minutes=30)
    db_session.add(appointment)
    db_session.commit()


def _cancel_appointment(client: TestClient, auth_headers: dict[str, str], appointment_id: int):
    return client.post(
        f"/api/v1/appointments/{appointment_id}/cancel",
        headers=auth_headers,
        json={"notes": "cancelled-by-customer"},
    )


def test_flexible_policy_full_refund(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="flex", cancellation_policy_type="flexible")
    booking = _book(client, context, suffix="70001")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=2)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is not None
    assert refund.status == RefundStatus.SUCCEEDED
    assert refund.amount_minor == payment.amount_minor


def test_moderate_policy_partial_refund(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(
        client,
        auth_headers,
        suffix="moderate",
        cancellation_policy_type="moderate",
        cancellation_window_hours=24,
        price="100.00",
    )
    booking = _book(client, context, suffix="70002")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=6)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is not None
    assert refund.status == RefundStatus.SUCCEEDED
    assert 0 < refund.amount_minor < payment.amount_minor
    assert refund.amount_minor == 8000


def test_strict_policy_no_refund(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(
        client,
        auth_headers,
        suffix="strict",
        cancellation_policy_type="strict",
        cancellation_window_hours=48,
        price="80.00",
    )
    booking = _book(client, context, suffix="70003")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=12)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is None


def test_deposit_retained_scenario(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(
        client,
        auth_headers,
        suffix="deposit-retain",
        payment_type="deposit",
        deposit_amount_minor=1500,
        cancellation_policy_type="moderate",
        cancellation_window_hours=24,
        price="75.00",
    )
    booking = _book(client, context, suffix="70004")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=2)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    assert payment.payment_type == PaymentType.DEPOSIT
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is None


def test_refund_record_creation_and_success_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="creation", cancellation_policy_type="flexible")
    booking = _book(client, context, suffix="70005")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=5)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is not None
    assert refund.status == RefundStatus.SUCCEEDED
    assert refund.processed_at is not None


def test_refund_failure_handling(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="failure", cancellation_policy_type="flexible")
    booking = _book(client, context, suffix="70006")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=4)

    def _raise_refund_error(*args, **kwargs):
        raise RuntimeError("mock refund provider failure")

    monkeypatch.setattr(
        "app.services.payments.mock_provider.MockRefundProvider.create_refund",
        _raise_refund_error,
    )

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is not None
    assert refund.status == RefundStatus.FAILED


def test_cancellation_triggers_refund_calculation(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(
        client,
        auth_headers,
        suffix="calc",
        cancellation_policy_type="strict",
        cancellation_window_hours=48,
        price="60.00",
    )
    booking = _book(client, context, suffix="70007")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=72)

    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    refund = db_session.scalar(select(Refund).where(Refund.payment_id == payment.id))
    assert refund is not None
    assert refund.amount_minor == 3000


def test_customer_booking_retrieval_shows_refund_summary(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="customer-summary", cancellation_policy_type="flexible")
    booking = _book(client, context, suffix="70008")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    _set_appointment_hours_before_start(db_session, appointment_id=booking["appointment_id"], hours_before_start=5)
    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["payment"]["refund_status"] == RefundStatus.SUCCEEDED.value
    assert payload["payment"]["refund_amount_minor"] is not None
    assert payload["payment"]["refund_processed_at"] is not None


def test_unpaid_booking_cancellation_produces_no_refund(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="unpaid", requires_payment=False)
    booking = _book(client, context, suffix="70009")
    assert booking["status"] == AppointmentStatus.CONFIRMED.value
    cancelled = _cancel_appointment(client, auth_headers, booking["appointment_id"])
    assert cancelled.status_code == 200, cancelled.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is None
    refunds = list(db_session.scalars(select(Refund)))
    assert refunds == []


def test_manual_refund_endpoint_for_admin_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="manual", cancellation_policy_type="flexible")
    booking = _book(client, context, suffix="70010")
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    assert payment.status == PaymentStatus.SUCCEEDED

    response = client.post(
        f"/api/v1/payments/{payment.id}/refund",
        headers=auth_headers,
        json={"amount_minor": 2000},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == RefundStatus.SUCCEEDED.value
    assert payload["amount_minor"] == 2000


def test_existing_payment_enforcement_still_works(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="compat", requires_payment=True, cancellation_policy_type="flexible")
    first = _book(client, context, suffix="70011")
    assert first["status"] == AppointmentStatus.PENDING_PAYMENT.value
    second = client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": context["organization_id"],
            "location_id": context["location_id"],
            "provider_id": context["provider_id"],
            "service_id": context["service_id"],
            "scheduled_start": context["slot_start"],
            "customer_name": "Phase53 Customer 70012",
            "customer_phone": "+155590070012",
            "customer_email": "phase53-70012@test.local",
            "preferred_language": "en",
        },
    )
    assert second.status_code == 400

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == first["appointment_id"]))
    assert payment is not None
    assert payment.status in {PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION}
