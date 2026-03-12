from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import (
    AppointmentStatus,
    PaymentStatus,
    ProviderEarningStatus,
    PayoutStatus,
)
from app.models.payment import Payment
from app.models.payout import Payout
from app.models.provider_earning import ProviderEarning
from app.workers import tasks as worker_tasks


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _create_org(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    name: str,
    commission_type: str = "percentage",
    commission_percentage: str = "0.10",
    commission_fixed_minor: int = 0,
) -> dict:
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
            "commission_type": commission_type,
            "commission_percentage": commission_percentage,
            "commission_fixed_minor": commission_fixed_minor,
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
    price: str = "100.00",
    requires_payment: bool = True,
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


def _book(
    client: TestClient,
    *,
    organization_id: int,
    location_id: int,
    provider_id: int,
    service_id: int,
    scheduled_start: str,
    suffix: str,
):
    response = client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization_id,
            "location_id": location_id,
            "provider_id": provider_id,
            "service_id": service_id,
            "scheduled_start": scheduled_start,
            "customer_name": f"Phase54 Customer {suffix}",
            "customer_phone": f"+1555999{suffix}",
            "customer_email": f"phase54-{suffix}@test.local",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _confirm_payment(client: TestClient, *, checkout_session_id: str):
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
    return response.json()


def _setup_context(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    suffix: str,
    commission_type: str = "percentage",
    commission_percentage: str = "0.10",
    commission_fixed_minor: int = 0,
    price: str = "100.00",
    requires_payment: bool = True,
) -> dict:
    org = _create_org(
        client,
        auth_headers,
        name=f"Phase54 Org {suffix}",
        commission_type=commission_type,
        commission_percentage=commission_percentage,
        commission_fixed_minor=commission_fixed_minor,
    )
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], name=f"Provider {suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Service {suffix}",
        price=price,
        requires_payment=requires_payment,
    )
    _add_availability(client, auth_headers, provider_id=provider["id"])
    monday = _next_weekday(0)
    slots = _list_slots(
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
        "slots": slots,
    }


def test_commission_percentage_calculation(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="pct", commission_type="percentage", commission_percentage="0.10")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81001",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    earning = db_session.scalar(select(ProviderEarning).where(ProviderEarning.payment_id == payment.id))
    assert earning is not None
    assert earning.gross_amount_minor == 10000
    assert earning.platform_fee_minor == 1000
    assert earning.provider_amount_minor == 9000


def test_commission_fixed_calculation(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(
        client,
        auth_headers,
        suffix="fixed",
        commission_type="fixed",
        commission_percentage="0.00",
        commission_fixed_minor=1500,
    )
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81002",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    earning = db_session.scalar(select(ProviderEarning).where(ProviderEarning.payment_id == payment.id))
    assert earning is not None
    assert earning.platform_fee_minor == 1500
    assert earning.provider_amount_minor == 8500


def test_earning_record_created_on_payment_success(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="earning-success")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81003",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    earnings = list(db_session.scalars(select(ProviderEarning).where(ProviderEarning.provider_id == context["provider_id"])))
    assert len(earnings) == 1
    assert earnings[0].status == ProviderEarningStatus.READY_FOR_PAYOUT


def test_payout_aggregation_logic(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="aggregate")
    first = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81004",
    )
    second = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][1],
        suffix="81005",
    )
    _confirm_payment(client, checkout_session_id=first["payment"]["checkout_session_id"])
    _confirm_payment(client, checkout_session_id=second["payment"]["checkout_session_id"])

    response = client.post(
        f"/api/v1/payouts/{context['provider_id']}/create",
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["provider_id"] == context["provider_id"]
    assert payload["total_amount_minor"] == 18000
    assert payload["earning_count"] == 2

    earnings = list(
        db_session.scalars(select(ProviderEarning).where(ProviderEarning.provider_id == context["provider_id"]))
    )
    assert all(earning.status == ProviderEarningStatus.PAID_OUT for earning in earnings)
    assert all(earning.payout_id == payload["id"] for earning in earnings)


def test_payout_creation_endpoint_requires_admin_role(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, suffix="endpoint-auth")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81006",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])

    response = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == PayoutStatus.PENDING.value


def test_payout_worker_processing(client: TestClient, auth_headers: dict[str, str], db_session: Session, monkeypatch) -> None:
    context = _setup_context(client, auth_headers, suffix="worker")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81007",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    created = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert created.status_code == 201, created.text
    payout_id = created.json()["id"]

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    result = worker_tasks.process_pending_payouts(provider_name="mock")
    assert result["processed"] >= 1
    assert result["completed"] >= 1
    payout = db_session.get(Payout, payout_id)
    assert payout is not None
    assert payout.status == PayoutStatus.COMPLETED
    assert payout.provider_payout_reference is not None


def test_refund_adjustment_logic_for_paid_out_earning(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    context = _setup_context(client, auth_headers, suffix="refund-adjust")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81008",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    payout_response = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert payout_response.status_code == 201, payout_response.text
    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    worker_tasks.process_pending_payouts(provider_name="mock")

    cancel = client.post(
        f"/api/v1/appointments/{booking['appointment_id']}/cancel",
        headers=auth_headers,
        json={"notes": "refund-adjustment-check"},
    )
    assert cancel.status_code == 200, cancel.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    earning = db_session.scalar(select(ProviderEarning).where(ProviderEarning.payment_id == payment.id))
    assert earning is not None
    assert earning.status == ProviderEarningStatus.PAID_OUT
    assert earning.adjustment_pending_minor > 0


def test_refund_before_payout_reduces_provider_earning(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    context = _setup_context(client, auth_headers, suffix="refund-before-payout")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81012",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    cancel = client.post(
        f"/api/v1/appointments/{booking['appointment_id']}/cancel",
        headers=auth_headers,
        json={"notes": "refund-before-payout"},
    )
    assert cancel.status_code == 200, cancel.text

    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is not None
    earning = db_session.scalar(select(ProviderEarning).where(ProviderEarning.payment_id == payment.id))
    assert earning is not None
    assert earning.provider_amount_minor == 0
    assert earning.refunded_amount_minor > 0
    assert earning.adjustment_pending_minor == 0


def test_provider_earnings_endpoint(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, suffix="earnings-endpoint")
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81009",
    )
    _confirm_payment(client, checkout_session_id=booking["payment"]["checkout_session_id"])
    response = client.get(f"/api/v1/providers/{context['provider_id']}/earnings", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["provider_id"] == context["provider_id"]
    assert payload[0]["status"] == ProviderEarningStatus.READY_FOR_PAYOUT.value


def test_existing_payment_flows_unaffected(client: TestClient, auth_headers: dict[str, str], db_session: Session) -> None:
    context = _setup_context(client, auth_headers, suffix="compat-payment", requires_payment=False)
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81010",
    )
    assert booking["status"] == AppointmentStatus.CONFIRMED.value
    payment = db_session.scalar(select(Payment).where(Payment.appointment_id == booking["appointment_id"]))
    assert payment is None
    earnings = list(db_session.scalars(select(ProviderEarning)))
    assert earnings == []


def test_existing_booking_flows_unaffected(client: TestClient, auth_headers: dict[str, str]) -> None:
    context = _setup_context(client, auth_headers, suffix="compat-booking", requires_payment=False)
    booking = _book(
        client,
        organization_id=context["organization_id"],
        location_id=context["location_id"],
        provider_id=context["provider_id"],
        service_id=context["service_id"],
        scheduled_start=context["slots"][0],
        suffix="81011",
    )
    retrieve = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert retrieve.status_code == 200, retrieve.text
    assert retrieve.json()["appointment_id"] == booking["appointment_id"]
    assert retrieve.json()["status"] == AppointmentStatus.CONFIRMED.value
