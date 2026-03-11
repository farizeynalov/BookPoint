from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _to_local_datetime(value: str, timezone_name: str = "Asia/Baku") -> datetime:
    return datetime.fromisoformat(value).astimezone(ZoneInfo(timezone_name))


def _find_slot_start(slots: list[dict], *, hour: int, minute: int) -> str:
    for slot in slots:
        local_start = _to_local_datetime(slot["start_datetime"])
        if local_start.hour == hour and local_start.minute == minute:
            return slot["start_datetime"]
    raise AssertionError(f"Slot with local start {hour:02d}:{minute:02d} was not found.")


def _get_default_location_id(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.get(f"/api/v1/organizations/{organization_id}/locations", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["id"]


def _create_provider_setup(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    duration_minutes: int = 30,
    buffer_before_minutes: int = 0,
    buffer_after_minutes: int = 0,
    availability_start: str = "09:00:00",
    availability_end: str = "11:00:00",
) -> dict[str, int]:
    org = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Buffer Org",
            "business_type": "salon",
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
            "display_name": "Buffer Provider",
            "title": "Specialist",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    ).json()
    service = client.post(
        f"/api/v1/providers/{provider['id']}/services",
        headers=auth_headers,
        json={
            "name": "Buffer Service",
            "description": None,
            "duration_minutes": duration_minutes,
            "price": "50.00",
            "currency": "USD",
            "buffer_before_minutes": buffer_before_minutes,
            "buffer_after_minutes": buffer_after_minutes,
            "is_active": True,
        },
    ).json()
    client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider["id"],
            "weekday": 0,
            "start_time": availability_start,
            "end_time": availability_end,
            "is_active": True,
        },
    )
    customer_one = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Buffer Customer One",
            "phone_number": "+1000000101",
            "email": "buffer-one@test.local",
            "preferred_language": "en",
        },
    ).json()
    customer_two = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Buffer Customer Two",
            "phone_number": "+1000000102",
            "email": "buffer-two@test.local",
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


def _get_slots(
    client: TestClient,
    auth_headers: dict[str, str],
    provider_id: int,
    monday: date,
    location_id: int,
    service_id: int | None = None,
) -> list[dict]:
    params = {
        "start_date": monday.isoformat(),
        "end_date": monday.isoformat(),
    }
    if service_id is not None:
        params["service_id"] = service_id
    params["location_id"] = location_id
    response = client.get(
        f"/api/v1/scheduling/providers/{provider_id}/slots",
        headers=auth_headers,
        params=params,
    )
    assert response.status_code == 200
    return response.json()


def test_service_without_buffers_behaves_like_before(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    assert len(slots) == 4
    first_local = _to_local_datetime(slots[0]["start_datetime"])
    assert first_local.hour == 9 and first_local.minute == 0


def test_slot_generation_respects_buffer_before(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_before_minutes=15)
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    local_starts = [(_to_local_datetime(slot["start_datetime"]).hour, _to_local_datetime(slot["start_datetime"]).minute) for slot in slots]
    assert local_starts == [(9, 15), (9, 45), (10, 15)]


def test_slot_generation_respects_buffer_after(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_after_minutes=15)
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    local_starts = [(_to_local_datetime(slot["start_datetime"]).hour, _to_local_datetime(slot["start_datetime"]).minute) for slot in slots]
    assert local_starts == [(9, 0), (9, 30), (10, 0)]


def test_slot_rejected_when_full_block_exceeds_availability(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(
        client,
        auth_headers,
        buffer_before_minutes=20,
        buffer_after_minutes=20,
        availability_start="09:00:00",
        availability_end="10:00:00",
    )
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    assert slots == []


def test_existing_appointment_buffers_block_nearby_slots(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_after_minutes=30)
    monday = _next_weekday(0)
    initial_slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    first_start = _find_slot_start(initial_slots, hour=9, minute=30)
    blocked_candidate = _find_slot_start(initial_slots, hour=10, minute=0)

    create_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert create_response.status_code == 201

    updated_slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    updated_starts = {slot["start_datetime"] for slot in updated_slots}
    assert blocked_candidate not in updated_starts


def test_create_rejects_overlap_caused_only_by_buffers(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_after_minutes=30)
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    first_start = _find_slot_start(slots, hour=9, minute=30)
    buffered_overlap_start = _find_slot_start(slots, hour=10, minute=0)

    first_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_two_id"],
            "start_datetime": buffered_overlap_start,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert second_response.status_code == 400
    assert "overlapping appointment" in second_response.json()["detail"]


def test_reschedule_rejects_overlap_caused_only_by_buffers(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(
        client,
        auth_headers,
        buffer_before_minutes=15,
        availability_start="09:00:00",
        availability_end="12:00:00",
    )
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    first_start = _find_slot_start(slots, hour=9, minute=15)
    second_start = _find_slot_start(slots, hour=10, minute=45)
    overlap_on_reschedule_start = _find_slot_start(slots, hour=9, minute=45)

    first_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": first_start,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert first_response.status_code == 201
    second_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_two_id"],
            "start_datetime": second_start,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert second_response.status_code == 201
    second_appointment_id = second_response.json()["id"]

    reschedule_response = client.post(
        f"/api/v1/appointments/{second_appointment_id}/reschedule",
        headers=auth_headers,
        json={"start_datetime": overlap_on_reschedule_start},
    )
    assert reschedule_response.status_code == 400
    assert "overlapping appointment" in reschedule_response.json()["detail"]


def test_appointment_end_datetime_remains_visible_duration_only(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_before_minutes=10, buffer_after_minutes=20)
    monday = _next_weekday(0)
    slots = _get_slots(client, auth_headers, data["provider_id"], monday, data["location_id"], data["service_id"])
    start_datetime = slots[0]["start_datetime"]

    create_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": start_datetime,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    start = datetime.fromisoformat(payload["start_datetime"])
    end = datetime.fromisoformat(payload["end_datetime"])
    assert int((end - start).total_seconds() // 60) == 30


def test_slot_generation_requires_service_id(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, availability_start="09:00:00", availability_end="11:00:00")
    monday = _next_weekday(0)
    response = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "location_id": data["location_id"],
        },
    )
    assert response.status_code == 422
