from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.enums import AppointmentStatus, PaymentStatus, PaymentType
from app.models.payment import Payment


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
    currency: str = "USD",
):
    return client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": name,
            "description": None,
            "duration_minutes": 30,
            "price": price,
            "currency": currency,
            "requires_payment": requires_payment,
            "payment_type": payment_type,
            "deposit_amount_minor": deposit_amount_minor,
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )


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


def _create_discovery_booking(
    client: TestClient,
    *,
    organization_id: int,
    location_id: int,
    provider_id: int,
    service_id: int,
    scheduled_start: str,
    suffix: str,
):
    return client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization_id,
            "location_id": location_id,
            "provider_id": provider_id,
            "service_id": service_id,
            "scheduled_start": scheduled_start,
            "customer_name": f"Payment Customer {suffix}",
            "customer_phone": f"+1555700{suffix}",
            "customer_email": f"payment-{suffix}@test.local",
            "preferred_language": "en",
        },
    )


def _setup_bookable_context(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    name_suffix: str,
    requires_payment: bool = False,
    payment_type: str = "full",
    deposit_amount_minor: int | None = None,
    price: str = "25.00",
) -> dict:
    org = _create_org(client, auth_headers, name=f"Payment Org {name_suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Provider {name_suffix}")
    service_response = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Service {name_suffix}",
        requires_payment=requires_payment,
        payment_type=payment_type,
        deposit_amount_minor=deposit_amount_minor,
        price=price,
    )
    assert service_response.status_code == 201, service_response.text
    service = service_response.json()
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
        "organization": org,
        "location_id": location_id,
        "provider": provider,
        "service": service,
        "slot_start": slot_start,
    }


def _book_from_context(client: TestClient, context: dict, *, suffix: str) -> dict:
    response = _create_discovery_booking(
        client,
        organization_id=context["organization"]["id"],
        location_id=context["location_id"],
        provider_id=context["provider"]["id"],
        service_id=context["service"]["id"],
        scheduled_start=context["slot_start"],
        suffix=suffix,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_unpaid_booking_behaves_as_before_and_creates_no_payment_record(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_bookable_context(client, auth_headers, name_suffix="unpaid", requires_payment=False)
    payload = _book_from_context(client, context, suffix="50001")

    assert payload["status"] == AppointmentStatus.CONFIRMED.value
    assert payload["payment"]["payment_required"] is False
    assert payload["payment"]["payment_status"] is None
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == payload["appointment_id"]))
    assert payment is None


def test_booking_paid_full_service_creates_payment_record_and_checkout_session(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="paid-full",
        requires_payment=True,
        payment_type="full",
        price="30.00",
    )
    payload = _book_from_context(client, context, suffix="50002")

    assert payload["status"] == AppointmentStatus.PENDING.value
    payment_payload = payload["payment"]
    assert payment_payload["payment_required"] is True
    assert payment_payload["payment_status"] == PaymentStatus.REQUIRES_ACTION.value
    assert payment_payload["amount_due_minor"] == 3000
    assert payment_payload["currency"] == "USD"
    assert isinstance(payment_payload["checkout_url"], str)
    assert isinstance(payment_payload["checkout_session_id"], str)

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == payload["appointment_id"]))
    assert payment is not None
    assert payment.amount_minor == 3000
    assert payment.payment_type == PaymentType.FULL
    assert payment.status == PaymentStatus.REQUIRES_ACTION


def test_booking_deposit_service_creates_payment_record_with_deposit_amount(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="deposit",
        requires_payment=True,
        payment_type="deposit",
        deposit_amount_minor=700,
        price="35.00",
    )
    payload = _book_from_context(client, context, suffix="50003")

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == payload["appointment_id"]))
    assert payment is not None
    assert payment.amount_minor == 700
    assert payment.payment_type == PaymentType.DEPOSIT


def test_invalid_deposit_configuration_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_bookable_context(client, auth_headers, name_suffix="invalid-seed")
    response = _create_service(
        client,
        auth_headers,
        organization_id=context["organization"]["id"],
        provider_id=context["provider"]["id"],
        name="Invalid Deposit Service",
        requires_payment=True,
        payment_type="deposit",
        deposit_amount_minor=5000,
        price="20.00",
    )
    assert response.status_code == 422


def test_payment_confirmation_marks_payment_succeeded_and_triggers_notification_hook(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="confirm-success",
        requires_payment=True,
        payment_type="full",
        price="40.00",
    )
    booking = _book_from_context(client, context, suffix="50004")
    payment_summary = booking["payment"]

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.payments.service.enqueue_payment_succeeded_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    confirm = client.post(
        "/api/v1/payments/confirm",
        headers={"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key},
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": payment_summary["checkout_session_id"],
            "status": "succeeded",
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == PaymentStatus.SUCCEEDED.value
    assert confirm.json()["paid_at"] is not None
    assert captured == [booking["appointment_id"]]

    payment = db_session.scalar(select(Payment).where(Payment.id == confirm.json()["payment_id"]))
    assert payment is not None
    assert payment.status == PaymentStatus.SUCCEEDED
    appointment = db_session.get(Appointment, booking["appointment_id"])
    assert appointment is not None
    assert appointment.status == AppointmentStatus.CONFIRMED


def test_failed_payment_confirmation_marks_payment_failed_and_triggers_notification_hook(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="confirm-failed",
        requires_payment=True,
        payment_type="full",
        price="22.00",
    )
    booking = _book_from_context(client, context, suffix="50005")
    payment_summary = booking["payment"]

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.payments.service.enqueue_payment_failed_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    confirm = client.post(
        "/api/v1/payments/confirm",
        headers={"X-Payment-Webhook-Secret": settings.payment_webhook_secret or settings.secret_key},
        json={
            "provider_name": "mock",
            "provider_checkout_session_id": payment_summary["checkout_session_id"],
            "status": "failed",
        },
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == PaymentStatus.FAILED.value
    assert captured == [booking["appointment_id"]]

    payment = db_session.scalar(select(Payment).where(Payment.id == confirm.json()["payment_id"]))
    assert payment is not None
    assert payment.status == PaymentStatus.FAILED
    appointment = db_session.get(Appointment, booking["appointment_id"])
    assert appointment is not None
    assert appointment.status == AppointmentStatus.PENDING


def test_customer_booking_retrieval_includes_safe_payment_summary(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="customer-summary",
        requires_payment=True,
        payment_type="full",
        price="27.00",
    )
    booking = _book_from_context(client, context, suffix="50006")
    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["payment"]["payment_required"] is True
    assert payload["payment"]["payment_status"] == PaymentStatus.REQUIRES_ACTION.value
    assert payload["payment"]["amount_due_minor"] == 2700
    assert "provider_payment_intent_id" not in payload["payment"]


def test_payment_required_booking_response_includes_checkout_data(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_bookable_context(
        client,
        auth_headers,
        name_suffix="checkout-data",
        requires_payment=True,
        payment_type="full",
        price="18.00",
    )
    booking = _book_from_context(client, context, suffix="50007")
    payment = booking["payment"]
    assert payment["payment_required"] is True
    assert payment["checkout_url"].startswith("https://mock-pay.bookpoint.local/checkout/")
    assert payment["checkout_session_id"].startswith("mock_cs_")


def test_existing_discovery_flow_for_unpaid_services_still_passes(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_bookable_context(client, auth_headers, name_suffix="unpaid-compat", requires_payment=False)
    booking = _book_from_context(client, context, suffix="50008")
    assert booking["status"] == AppointmentStatus.CONFIRMED.value
    assert "appointment_id" in booking
    assert "customer_id" in booking
    assert "booking_access_token" in booking


def test_existing_self_service_endpoints_still_pass(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_bookable_context(client, auth_headers, name_suffix="self-service-compat", requires_payment=False)
    booking = _book_from_context(client, context, suffix="50009")

    cancel = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == AppointmentStatus.CANCELLED.value


def test_existing_admin_provider_staff_flows_still_pass(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Payment Existing Flow Org")
    _create_provider(client, auth_headers, organization_id=org["id"], name="Flow Provider")

    with_auth = client.get("/api/v1/providers", headers=auth_headers)
    assert with_auth.status_code == 200

    without_auth = client.get("/api/v1/providers")
    assert without_auth.status_code == 401
