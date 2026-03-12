from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


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
            "price": "20.00",
            "currency": "USD",
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


def _list_discovery_slots(
    client: TestClient,
    *,
    provider_id: int,
    service_id: int,
    location_id: int,
    query_date: date,
) -> list[dict]:
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


def _create_discovery_booking(
    client: TestClient,
    *,
    organization_id: int,
    location_id: int,
    provider_id: int,
    service_id: int,
    scheduled_start: str,
    customer_name: str,
    customer_phone: str,
    customer_email: str,
):
    return client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization_id,
            "location_id": location_id,
            "provider_id": provider_id,
            "service_id": service_id,
            "scheduled_start": scheduled_start,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "preferred_language": "en",
        },
    )


def _bootstrap_booking_setup(client: TestClient, auth_headers: dict[str, str], *, name_suffix: str) -> dict:
    org = _create_org(client, auth_headers, name=f"Self Service Org {name_suffix}")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name=f"Provider {name_suffix}")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name=f"Service {name_suffix}",
    )
    _add_availability(client, auth_headers, provider_id=provider["id"])
    monday = _next_weekday(0)
    slots = _list_discovery_slots(
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
        "slots": slots,
    }


def test_booking_confirmation_returns_access_token_and_reference(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="confirm")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Self Service Customer",
        customer_phone="+15550050001",
        customer_email="selfservice-confirm@test.local",
    )
    assert booking.status_code == 201, booking.text
    payload = booking.json()
    assert payload["booking_reference"].startswith("BKP-")
    assert isinstance(payload["booking_access_token"], str) and len(payload["booking_access_token"]) > 20


def test_customer_can_retrieve_booking_with_valid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="retrieve")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Retrieve Customer",
        customer_phone="+15550050002",
        customer_email="selfservice-retrieve@test.local",
    ).json()

    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["appointment_id"] == booking["appointment_id"]


def test_customer_cannot_retrieve_booking_with_invalid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="invalid")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Invalid Token Customer",
        customer_phone="+15550050003",
        customer_email="selfservice-invalid@test.local",
    ).json()

    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": "invalid-token"},
    )
    assert response.status_code == 404


def test_customer_can_cancel_booking_with_valid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="cancel")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Cancel Customer",
        customer_phone="+15550050004",
        customer_email="selfservice-cancel@test.local",
    ).json()

    response = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


def test_customer_cancellation_triggers_notification_path(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="cancel-notify")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Cancel Notify Customer",
        customer_phone="+15550050005",
        customer_email="selfservice-cancel-notify@test.local",
    ).json()

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_cancelled_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    response = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    assert captured == [booking["appointment_id"]]


def test_customer_cannot_cancel_already_cancelled_booking(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="cancel-twice")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Cancel Twice Customer",
        customer_phone="+15550050006",
        customer_email="selfservice-cancel-twice@test.local",
    ).json()

    first = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/cancel",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert second.status_code == 400


def test_customer_can_reschedule_booking_with_valid_token(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="reschedule")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Reschedule Customer",
        customer_phone="+15550050007",
        customer_email="selfservice-reschedule@test.local",
    ).json()

    response = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/reschedule",
        headers={"X-Booking-Token": booking["booking_access_token"]},
        json={"scheduled_start": data["slots"][1]["start_datetime"]},
    )
    assert response.status_code == 200, response.text
    assert _parse_iso_datetime(response.json()["scheduled_start"]) == _parse_iso_datetime(data["slots"][1]["start_datetime"])


def test_customer_reschedule_rejects_unavailable_slot(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="reschedule-conflict")

    first = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="First Conflict",
        customer_phone="+15550050008",
        customer_email="selfservice-reschedule-conflict-1@test.local",
    ).json()
    second = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][1]["start_datetime"],
        customer_name="Second Conflict",
        customer_phone="+15550050009",
        customer_email="selfservice-reschedule-conflict-2@test.local",
    ).json()

    response = client.post(
        f"/api/v1/customer/bookings/{second['appointment_id']}/reschedule",
        headers={"X-Booking-Token": second["booking_access_token"]},
        json={"scheduled_start": first["scheduled_start"]},
    )
    assert response.status_code == 400


def test_customer_reschedule_triggers_notification_path(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="reschedule-notify")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Reschedule Notify Customer",
        customer_phone="+15550050010",
        customer_email="selfservice-reschedule-notify@test.local",
    ).json()

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_rescheduled_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    response = client.post(
        f"/api/v1/customer/bookings/{booking['appointment_id']}/reschedule",
        headers={"X-Booking-Token": booking["booking_access_token"]},
        json={"scheduled_start": data["slots"][1]["start_datetime"]},
    )
    assert response.status_code == 200, response.text
    assert captured == [booking["appointment_id"]]


def test_self_service_endpoints_do_not_leak_internal_fields(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="leak-check")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Leak Check Customer",
        customer_phone="+15550050011",
        customer_email="selfservice-leak@test.local",
    ).json()

    response = client.get(
        f"/api/v1/customer/bookings/{booking['appointment_id']}",
        headers={"X-Booking-Token": booking["booking_access_token"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "notes" not in payload
    assert "booking_access_token" not in payload
    assert "customer_id" not in payload


def test_existing_admin_provider_flows_still_pass(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Self Service Existing Flow Org")
    _create_provider(client, auth_headers, organization_id=org["id"], display_name="Existing Flow Provider")

    with_auth = client.get("/api/v1/providers", headers=auth_headers)
    assert with_auth.status_code == 200

    without_auth = client.get("/api/v1/providers")
    assert without_auth.status_code == 401


def test_discovery_booking_flow_still_works_unchanged(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_booking_setup(client, auth_headers, name_suffix="discovery-compat")
    booking = _create_discovery_booking(
        client,
        organization_id=data["organization"]["id"],
        location_id=data["location_id"],
        provider_id=data["provider"]["id"],
        service_id=data["service"]["id"],
        scheduled_start=data["slots"][0]["start_datetime"],
        customer_name="Discovery Compat Customer",
        customer_phone="+15550050012",
        customer_email="selfservice-discovery-compat@test.local",
    )
    assert booking.status_code == 201, booking.text
    payload = booking.json()
    assert "appointment_id" in payload
    assert "customer_id" in payload
    assert "booking_access_token" in payload
