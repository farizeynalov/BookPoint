from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import AppointmentStatus, PayoutStatus
from app.models.payment import Payment
from app.models.payout import Payout
from app.models.refund import Refund


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _configure_limits(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(settings, "enable_rate_limiting", True)
    monkeypatch.setattr(settings, "rate_limit_use_redis", False)
    monkeypatch.setattr(settings, "rate_limit_fallback_to_memory", True)
    for key, value in overrides.items():
        monkeypatch.setattr(settings, key, value)


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
    price: str = "70.00",
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
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    service_id: int,
    location_id: int,
    query_date: date,
) -> list[str]:
    response = client.get(
        f"/api/v1/scheduling/providers/{provider_id}/slots",
        headers=auth_headers,
        params={
            "start_date": query_date.isoformat(),
            "end_date": query_date.isoformat(),
            "service_id": service_id,
            "location_id": location_id,
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
    org = _create_org(client, auth_headers, name=f"Phase63 Org {suffix}")
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
        auth_headers,
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
            "customer_name": f"Phase63 Customer {suffix}",
            "customer_phone": f"+1555300{suffix}",
            "customer_email": f"phase63-{suffix}@test.local",
            "preferred_language": "en",
        },
    )


def _confirm_payment(
    client: TestClient,
    *,
    checkout_session_id: str,
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
            "status": "succeeded",
        },
    )


def _parse_metrics(payload: str) -> dict[str, float]:
    rows: dict[str, float] = {}
    for line in payload.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split(" ", 1)
        rows[key] = float(value)
    return rows


def test_public_slot_endpoint_rate_limited_after_threshold(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(monkeypatch, rate_limit_public_slots_limit=2, rate_limit_public_slots_window_seconds=60)
    context = _setup_context(client, auth_headers, suffix="slots-limit", requires_payment=False)

    endpoint = f"/api/v1/discovery/providers/{context['provider_id']}/slots"
    params = {
        "service_id": context["service_id"],
        "location_id": context["location_id"],
        "date": _next_weekday(0).isoformat(),
    }
    first = client.get(endpoint, params=params)
    second = client.get(endpoint, params=params)
    third = client.get(endpoint, params=params)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429


def test_public_booking_endpoint_rate_limited_after_threshold(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(
        monkeypatch,
        rate_limit_public_booking_limit=1,
        rate_limit_public_booking_window_seconds=60,
        rate_limit_public_booking_duplicate_limit=5,
        rate_limit_public_booking_duplicate_window_seconds=60,
    )
    context = _setup_context(client, auth_headers, suffix="booking-limit", requires_payment=False)
    first = _book(client, context=context, scheduled_start=context["slots"][0], suffix="93001")
    second = _book(client, context=context, scheduled_start=context["slots"][1], suffix="93002")
    assert first.status_code == 201, first.text
    assert second.status_code == 429


def test_customer_self_service_invalid_token_attempts_are_rate_limited(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(
        monkeypatch,
        rate_limit_customer_booking_get_limit=100,
        rate_limit_customer_invalid_token_limit=2,
        rate_limit_customer_invalid_token_window_seconds=60,
    )
    context = _setup_context(client, auth_headers, suffix="invalid-token", requires_payment=False)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="93003").json()

    first = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": "bad-token"},
    )
    second = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": "bad-token"},
    )
    third = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": "bad-token"},
    )
    assert first.status_code == 404
    assert second.status_code == 404
    assert third.status_code == 429


def test_payment_confirm_endpoint_rate_limited_safely(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_limits(monkeypatch, rate_limit_payment_confirm_limit=1, rate_limit_payment_confirm_window_seconds=60)
    context = _setup_context(client, auth_headers, suffix="confirm-limit", requires_payment=True)
    booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="93004").json()
    checkout_session = booking["payment"]["checkout_session_id"]

    first = _confirm_payment(client, checkout_session_id=checkout_session)
    second = _confirm_payment(client, checkout_session_id=checkout_session)
    assert first.status_code == 200, first.text
    assert second.status_code == 429

    payment = db_session.get(Payment, first.json()["payment_id"])
    assert payment is not None
    assert payment.status.value == "succeeded"


def test_authenticated_payout_and_refund_rate_limit_works(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_limits(
        monkeypatch,
        rate_limit_manual_refund_limit=1,
        rate_limit_manual_refund_window_seconds=60,
        rate_limit_payout_create_limit=1,
        rate_limit_payout_create_window_seconds=60,
    )
    context = _setup_context(client, auth_headers, suffix="auth-limits", requires_payment=True)
    first_booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="93005").json()
    second_booking = _book(client, context=context, scheduled_start=context["slots"][1], suffix="93006").json()
    first_confirm = _confirm_payment(client, checkout_session_id=first_booking["payment"]["checkout_session_id"])
    second_confirm = _confirm_payment(client, checkout_session_id=second_booking["payment"]["checkout_session_id"])
    assert first_confirm.status_code == 200, first_confirm.text
    assert second_confirm.status_code == 200, second_confirm.text

    first_refund = client.post(
        f"/api/v1/payments/{first_confirm.json()['payment_id']}/refund",
        headers=auth_headers,
        json={"amount_minor": 1000},
    )
    second_refund = client.post(
        f"/api/v1/payments/{first_confirm.json()['payment_id']}/refund",
        headers=auth_headers,
        json={"amount_minor": 1000},
    )
    assert first_refund.status_code == 200, first_refund.text
    assert second_refund.status_code == 429

    first_payout = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    second_payout = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert first_payout.status_code == 201, first_payout.text
    assert second_payout.status_code == 429

    payout = db_session.get(Payout, first_payout.json()["id"])
    assert payout is not None


def test_requests_under_threshold_still_succeed(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(monkeypatch, rate_limit_public_slots_limit=5, rate_limit_public_slots_window_seconds=60)
    context = _setup_context(client, auth_headers, suffix="under-threshold", requires_payment=False)
    endpoint = f"/api/v1/discovery/providers/{context['provider_id']}/slots"
    params = {
        "service_id": context["service_id"],
        "location_id": context["location_id"],
        "date": _next_weekday(0).isoformat(),
    }
    first = client.get(endpoint, params=params)
    second = client.get(endpoint, params=params)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text


def test_rate_limit_429_uses_standardized_error_envelope_and_retry_after(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(monkeypatch, rate_limit_public_slots_limit=1, rate_limit_public_slots_window_seconds=60)
    context = _setup_context(client, auth_headers, suffix="envelope", requires_payment=False)
    endpoint = f"/api/v1/discovery/providers/{context['provider_id']}/slots"
    params = {
        "service_id": context["service_id"],
        "location_id": context["location_id"],
        "date": _next_weekday(0).isoformat(),
    }
    first = client.get(endpoint, params=params)
    blocked = client.get(endpoint, params=params)
    assert first.status_code == 200, first.text
    assert blocked.status_code == 429
    body = blocked.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["request_id"] == blocked.headers["X-Request-ID"]
    assert body["error"]["details"]["retry_after_seconds"] >= 1
    assert int(blocked.headers["Retry-After"]) >= 1


def test_rate_limit_metrics_increment_correctly(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(monkeypatch, rate_limit_public_slots_limit=1, rate_limit_public_slots_window_seconds=60)
    context = _setup_context(client, auth_headers, suffix="metrics", requires_payment=False)
    endpoint = f"/api/v1/discovery/providers/{context['provider_id']}/slots"
    params = {
        "service_id": context["service_id"],
        "location_id": context["location_id"],
        "date": _next_weekday(0).isoformat(),
    }
    allowed = client.get(endpoint, params=params)
    blocked = client.get(endpoint, params=params)
    assert allowed.status_code == 200
    assert blocked.status_code == 429

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200, metrics_response.text
    metrics = _parse_metrics(metrics_response.text)
    assert metrics["rate_limit_allowed_total"] >= 1
    assert metrics["rate_limit_hits_total"] >= 1


def test_idempotent_replay_still_works_under_rate_limiting(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    _configure_limits(
        monkeypatch,
        rate_limit_public_booking_limit=1,
        rate_limit_public_booking_window_seconds=60,
        rate_limit_public_booking_duplicate_limit=1,
        rate_limit_public_booking_duplicate_window_seconds=60,
    )
    context = _setup_context(client, auth_headers, suffix="idem-replay", requires_payment=False)
    idem_key = "phase63-idem-key"
    first = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="93007",
        idempotency_key=idem_key,
    )
    second = _book(
        client,
        context=context,
        scheduled_start=context["slots"][0],
        suffix="93007",
        idempotency_key=idem_key,
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.headers.get("X-Idempotent-Replayed") == "true"


def test_existing_major_booking_payment_refund_payout_flows_still_pass(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
    monkeypatch,
) -> None:
    _configure_limits(
        monkeypatch,
        rate_limit_public_booking_limit=50,
        rate_limit_public_slots_limit=100,
        rate_limit_manual_refund_limit=50,
        rate_limit_payout_create_limit=50,
        rate_limit_payment_confirm_limit=100,
    )
    context = _setup_context(client, auth_headers, suffix="compat", requires_payment=True)
    first_booking = _book(client, context=context, scheduled_start=context["slots"][0], suffix="93008").json()
    second_booking = _book(client, context=context, scheduled_start=context["slots"][1], suffix="93009").json()
    first_confirm = _confirm_payment(client, checkout_session_id=first_booking["payment"]["checkout_session_id"])
    second_confirm = _confirm_payment(client, checkout_session_id=second_booking["payment"]["checkout_session_id"])
    assert first_confirm.status_code == 200, first_confirm.text
    assert second_confirm.status_code == 200, second_confirm.text

    refund = client.post(
        f"/api/v1/payments/{first_confirm.json()['payment_id']}/refund",
        headers=auth_headers,
        json={"amount_minor": 1000},
    )
    assert refund.status_code == 200, refund.text

    payout = client.post(f"/api/v1/payouts/{context['provider_id']}/create", headers=auth_headers)
    assert payout.status_code == 201, payout.text

    payment_record = db_session.get(Payment, first_confirm.json()["payment_id"])
    payout_record = db_session.get(Payout, payout.json()["id"])
    assert payment_record is not None
    assert payout_record is not None
    assert payout_record.status in {PayoutStatus.PENDING, PayoutStatus.PROCESSING, PayoutStatus.COMPLETED}

    refunds = list(db_session.scalars(select(Refund).where(Refund.payment_id == payment_record.id)))
    assert refunds
    assert first_booking["status"] == AppointmentStatus.PENDING_PAYMENT.value
