from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import User


LOCAL_TIMEZONE = ZoneInfo("Asia/Baku")


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _to_local_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(LOCAL_TIMEZONE)


def _local_time_points(slots: list[dict]) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for slot in slots:
        local_start = _to_local_datetime(slot["start_datetime"])
        points.append((local_start.hour, local_start.minute))
    return points


def _local_to_utc_iso(target_date: date, target_time: time) -> str:
    local_dt = datetime.combine(target_date, target_time).replace(tzinfo=LOCAL_TIMEZONE)
    return local_dt.astimezone(timezone.utc).isoformat()


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
) -> dict[str, int]:
    org = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Schedule Refinement Org",
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
            "display_name": "Schedule Provider",
            "title": "Consultant",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    ).json()
    service = client.post(
        f"/api/v1/providers/{provider['id']}/services",
        headers=auth_headers,
        json={
            "name": "Schedule Service",
            "description": None,
            "duration_minutes": duration_minutes,
            "price": "40.00",
            "currency": "USD",
            "buffer_before_minutes": buffer_before_minutes,
            "buffer_after_minutes": buffer_after_minutes,
            "is_active": True,
        },
    ).json()
    customer_one = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Schedule Customer One",
            "phone_number": "+1000000201",
            "email": "schedule-one@test.local",
            "preferred_language": "en",
        },
    ).json()
    customer_two = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Schedule Customer Two",
            "phone_number": "+1000000202",
            "email": "schedule-two@test.local",
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


def _add_weekly_availability(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    weekday: int,
    start_time: str,
    end_time: str,
) -> None:
    response = client.post(
        f"/api/v1/providers/{provider_id}/availability",
        headers=auth_headers,
        json={
            "weekday": weekday,
            "start_time": start_time,
            "end_time": end_time,
            "is_active": True,
        },
    )
    assert response.status_code == 201


def _create_date_override(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    override_date: date,
    is_available: bool,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/providers/{provider_id}/date-overrides",
        headers=auth_headers,
        json={
            "override_date": override_date.isoformat(),
            "is_available": is_available,
            "start_time": start_time,
            "end_time": end_time,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_time_off(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    start_datetime: str,
    end_datetime: str,
    reason: str = "time off",
) -> dict:
    response = client.post(
        f"/api/v1/providers/{provider_id}/time-off",
        headers=auth_headers,
        json={
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "reason": reason,
        },
    )
    assert response.status_code == 201
    return response.json()


def _get_slots(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    provider_id: int,
    query_date: date,
    location_id: int,
    service_id: int,
) -> list[dict]:
    response = client.get(
        f"/api/v1/scheduling/providers/{provider_id}/slots",
        headers=auth_headers,
        params={
            "start_date": query_date.isoformat(),
            "end_date": query_date.isoformat(),
            "location_id": location_id,
            "service_id": service_id,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_weekly_availability_creates_usable_slots(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        weekday=0,
        start_time="09:00:00",
        end_time="11:00:00",
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert len(slots) == 4


def test_multiple_windows_in_one_day_work(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="11:00:00")
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="14:00:00", end_time="16:00:00")
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    starts = _local_time_points(slots)
    assert len(starts) == 8
    assert (9, 0) in starts
    assert (14, 0) in starts


def test_split_windows_block_middle_break(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="13:00:00")
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="14:00:00", end_time="18:00:00")
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    starts = _local_time_points(slots)
    assert (13, 0) not in starts
    assert (12, 30) in starts
    assert (14, 0) in starts


def test_full_day_unavailable_override_removes_slots(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="11:00:00")
    _create_date_override(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        override_date=monday,
        is_available=False,
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert slots == []


def test_custom_hours_override_replaces_weekly_hours(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="18:00:00")
    _create_date_override(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        override_date=monday,
        is_available=True,
        start_time="12:00:00",
        end_time="17:00:00",
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    starts = _local_time_points(slots)
    assert starts[0] == (12, 0)
    assert starts[-1] == (16, 30)
    assert (9, 0) not in starts


def test_time_off_removes_overlapping_slots(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="12:00:00")
    _create_time_off(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        start_datetime=_local_to_utc_iso(monday, time.fromisoformat("10:00:00")),
        end_datetime=_local_to_utc_iso(monday, time.fromisoformat("11:00:00")),
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert _local_time_points(slots) == [(9, 0), (9, 30), (11, 0), (11, 30)]


def test_create_and_list_provider_time_off(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    created = _create_time_off(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        start_datetime=_local_to_utc_iso(monday, time.fromisoformat("10:00:00")),
        end_datetime=_local_to_utc_iso(monday, time.fromisoformat("11:00:00")),
    )
    response = client.get(
        f"/api/v1/providers/{data['provider_id']}/time-off",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == created["id"]
    assert payload[0]["provider_id"] == data["provider_id"]


def test_invalid_time_off_rejected_when_start_not_before_end(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    same_point = _local_to_utc_iso(monday, time.fromisoformat("10:00:00"))
    response = client.post(
        f"/api/v1/providers/{data['provider_id']}/time-off",
        headers=auth_headers,
        json={
            "start_datetime": same_point,
            "end_datetime": same_point,
            "reason": "invalid interval",
        },
    )
    assert response.status_code == 400
    assert "start_datetime must be before end_datetime" in response.json()["detail"]


def test_create_and_list_provider_date_override(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    created = _create_date_override(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        override_date=monday,
        is_available=True,
        start_time="12:00:00",
        end_time="15:00:00",
    )
    response = client.get(
        f"/api/v1/providers/{data['provider_id']}/date-overrides",
        headers=auth_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == created["id"]
    assert payload[0]["provider_id"] == data["provider_id"]


def test_buffer_aware_scheduling_still_works(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers, buffer_before_minutes=15, buffer_after_minutes=15)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="11:00:00")
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert _local_time_points(slots) == [(9, 15), (9, 45), (10, 15)]


def test_full_window_time_off_returns_no_slots(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="12:00:00")
    _create_time_off(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        start_datetime=_local_to_utc_iso(monday, time.fromisoformat("09:00:00")),
        end_datetime=_local_to_utc_iso(monday, time.fromisoformat("12:00:00")),
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert slots == []


def test_time_off_subtracts_from_override_hours(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="18:00:00")
    _create_date_override(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        override_date=monday,
        is_available=True,
        start_time="12:00:00",
        end_time="15:00:00",
    )
    _create_time_off(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        start_datetime=_local_to_utc_iso(monday, time.fromisoformat("13:00:00")),
        end_datetime=_local_to_utc_iso(monday, time.fromisoformat("14:00:00")),
    )
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
    assert _local_time_points(slots) == [(12, 0), (12, 30), (14, 0), (14, 30)]


def test_appointment_creation_respects_refined_schedule(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="10:00:00")
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="11:00:00", end_time="12:00:00")

    invalid_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": _local_to_utc_iso(monday, time.fromisoformat("10:30:00")),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert invalid_response.status_code == 400
    assert "fit provider availability" in invalid_response.json()["detail"]

    valid_response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": data["location_id"],
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_one_id"],
            "start_datetime": _local_to_utc_iso(monday, time.fromisoformat("11:00:00")),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert valid_response.status_code == 201


def test_rescheduling_respects_refined_schedule(client: TestClient, auth_headers: dict[str, str]) -> None:
    data = _create_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    _add_weekly_availability(client, auth_headers, provider_id=data["provider_id"], weekday=0, start_time="09:00:00", end_time="11:00:00")
    slots = _get_slots(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        query_date=monday,
        location_id=data["location_id"],
        service_id=data["service_id"],
    )
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
    appointment_id = create_response.json()["id"]

    _create_date_override(
        client,
        auth_headers,
        provider_id=data["provider_id"],
        override_date=monday,
        is_available=False,
    )
    reschedule_response = client.post(
        f"/api/v1/appointments/{appointment_id}/reschedule",
        headers=auth_headers,
        json={"start_datetime": _local_to_utc_iso(monday, time.fromisoformat("09:30:00"))},
    )
    assert reschedule_response.status_code == 400
    assert "fit provider availability" in reschedule_response.json()["detail"]


def test_schedule_management_endpoints_enforce_org_access(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    data = _create_provider_setup(client, auth_headers)
    outsider = User(
        email="outsider@test.local",
        hashed_password=get_password_hash("outsider123"),
        full_name="Outsider",
        is_active=True,
        is_platform_admin=False,
    )
    db_session.add(outsider)
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": outsider.email, "password": "outsider123"},
    )
    outsider_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    availability_response = client.post(
        f"/api/v1/providers/{data['provider_id']}/availability",
        headers=outsider_headers,
        json={
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert availability_response.status_code == 403

    override_response = client.post(
        f"/api/v1/providers/{data['provider_id']}/date-overrides",
        headers=outsider_headers,
        json={
            "override_date": _next_weekday(0).isoformat(),
            "is_available": False,
            "start_time": None,
            "end_time": None,
            "is_active": True,
        },
    )
    assert override_response.status_code == 403

    time_off_response = client.post(
        f"/api/v1/providers/{data['provider_id']}/time-off",
        headers=outsider_headers,
        json={
            "start_datetime": datetime.now(timezone.utc).isoformat(),
            "end_datetime": (datetime.now(timezone.utc)).isoformat(),
            "reason": "unauthorized",
        },
    )
    assert time_off_response.status_code == 403
