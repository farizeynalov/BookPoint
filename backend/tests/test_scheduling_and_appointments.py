from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _get_default_location_id(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.get(f"/api/v1/organizations/{organization_id}/locations", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["id"]


def _bootstrap_provider_setup(client: TestClient, auth_headers: dict[str, str]) -> dict[str, int]:
    org = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Scheduling Org",
            "business_type": "clinic",
            "city": "Baku",
            "address": "Main",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    ).json()
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": org["id"],
            "user_id": None,
            "display_name": "Dr Slot",
            "title": "Doctor",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    ).json()
    service = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": org["id"],
            "provider_id": provider["id"],
            "name": "Consultation",
            "description": None,
            "duration_minutes": 30,
            "price": "40.00",
            "is_active": True,
        },
    ).json()
    client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider["id"],
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    customer_one = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Customer One",
            "phone_number": "+1000000001",
            "email": "customer1@test.local",
            "preferred_language": "en",
        },
    ).json()
    customer_two = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Customer Two",
            "phone_number": "+1000000002",
            "email": "customer2@test.local",
            "preferred_language": "en",
        },
    ).json()
    return {
        "organization_id": org["id"],
        "location_id": location_id,
        "provider_id": provider["id"],
        "service_id": service["id"],
        "customer_one_id": customer_one["id"],
        "customer_two_id": customer_two["id"],
    }


def test_slot_generation(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    assert response.status_code == 200
    slots = response.json()
    assert len(slots) == 4


def test_appointment_creation_and_overlap_prevention(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    first_slot = slots_response.json()[0]
    first_start = datetime.fromisoformat(first_slot["start_datetime"])
    assert first_start.tzinfo is not None

    create_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "organization_id": data["organization_id"],
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start.isoformat(),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": "First booking",
        },
    )
    assert create_response.status_code == 201

    overlap_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "organization_id": data["organization_id"],
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_two_id"],
            "start_datetime": first_start.isoformat(),
            "status": "confirmed",
            "booking_channel": "mobile",
            "notes": "Overlap booking",
        },
    )
    assert overlap_response.status_code == 400
    assert "overlapping appointment" in overlap_response.json()["detail"]

    list_response = client.get(
        "/api/v1/appointments",
        headers=auth_headers,
        params={"organization_id": data["organization_id"]},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_reschedule_keeps_pending_status(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    slots = slots_response.json()
    first_start = datetime.fromisoformat(slots[0]["start_datetime"])
    second_start = datetime.fromisoformat(slots[1]["start_datetime"])

    create_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start.isoformat(),
            "status": "pending",
            "booking_channel": "web",
            "notes": "Pending appointment",
        },
    )
    assert create_response.status_code == 201
    appointment = create_response.json()
    assert appointment["status"] == "pending"

    reschedule_response = client.post(
        f"/api/v1/appointments/{appointment['id']}/reschedule",
        headers=auth_headers,
        json={"start_datetime": second_start.isoformat()},
    )
    assert reschedule_response.status_code == 200
    updated = reschedule_response.json()
    assert updated["status"] == "pending"
    assert updated["start_datetime"] == second_start.isoformat()


def test_appointment_rejects_mismatched_organization_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    other_org = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Other Org",
            "business_type": "clinic",
            "city": "Baku",
            "address": "Other",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    ).json()

    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    first_start = datetime.fromisoformat(slots_response.json()[0]["start_datetime"])

    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "organization_id": other_org["id"],
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start.isoformat(),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert "organization_id does not match provider organization" in response.json()["detail"]


def test_cancelled_appointment_cannot_be_rescheduled(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    first_start = datetime.fromisoformat(slots_response.json()[0]["start_datetime"])
    second_start = datetime.fromisoformat(slots_response.json()[1]["start_datetime"])

    created = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start.isoformat(),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    ).json()

    cancel_response = client.post(
        f"/api/v1/appointments/{created['id']}/cancel",
        headers=auth_headers,
        json={"notes": "cancelled"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    reschedule_response = client.post(
        f"/api/v1/appointments/{created['id']}/reschedule",
        headers=auth_headers,
        json={"start_datetime": second_start.isoformat()},
    )
    assert reschedule_response.status_code == 400
    assert "pending or confirmed" in reschedule_response.json()["detail"]


def test_new_appointment_status_must_be_pending_or_confirmed(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
            "location_id": data["location_id"],
        },
    )
    first_start = datetime.fromisoformat(slots_response.json()[0]["start_datetime"])

    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start.isoformat(),
            "status": "completed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert "pending or confirmed" in response.json()["detail"]
