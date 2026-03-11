from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import User


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _create_user(db_session: Session, *, email: str, full_name: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("password123"),
        full_name=full_name,
        is_active=True,
        is_platform_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _auth_headers(client: TestClient, *, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _get_default_location_id(client: TestClient, headers: dict[str, str], organization_id: int) -> int:
    response = client.get(f"/api/v1/organizations/{organization_id}/locations", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["id"]


def _create_org(client: TestClient, headers: dict[str, str], *, name: str = "Capabilities Org") -> dict:
    response = client.post("/api/v1/organizations", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    payload = response.json()
    payload["location_id"] = _get_default_location_id(client, headers, payload["id"])
    return payload


def _create_provider(
    client: TestClient,
    headers: dict[str, str],
    *,
    organization_id: int,
    display_name: str,
    user_id: int | None = None,
) -> dict:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "organization_id": organization_id,
            "user_id": user_id,
            "display_name": display_name,
            "title": None,
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_service(
    client: TestClient,
    headers: dict[str, str],
    *,
    organization_id: int,
    provider_id: int,
    name: str = "Service",
    duration_minutes: int = 30,
) -> dict:
    response = client.post(
        "/api/v1/services",
        headers=headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": name,
            "description": None,
            "duration_minutes": duration_minutes,
            "price": "25.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_member(
    client: TestClient,
    headers: dict[str, str],
    *,
    organization_id: int,
    user_id: int,
    role: str,
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers=headers,
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_assign_service_to_provider(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers)
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider_one["id"],
        name="Haircut",
    )

    assign = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"]},
    )
    assert assign.status_code == 201, assign.text
    payload = assign.json()
    assert payload["id"] == service["id"]
    assert payload["provider_id"] == provider_two["id"]
    assert payload["duration_minutes_override"] is None


def test_duplicate_assignment_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Duplicate Assignment Org")
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_one["id"], name="Fade")

    first = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"]},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"]},
    )
    assert second.status_code == 409


def test_provider_service_org_mismatch_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    org_one = _create_org(client, auth_headers, name="Org One")
    org_two = _create_org(client, auth_headers, name="Org Two")
    provider_one = _create_provider(client, auth_headers, organization_id=org_one["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org_two["id"], display_name="Provider Two")
    service = _create_service(client, auth_headers, organization_id=org_one["id"], provider_id=provider_one["id"], name="Trim")

    response = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider and service organization mismatch"


def test_list_services_for_provider_and_services_query_filter(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="List Filter Org")
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service_one = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_one["id"], name="Service One")
    service_two = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_two["id"], name="Service Two")

    assign = client.post(
        f"/api/v1/providers/{provider_one['id']}/services",
        headers=auth_headers,
        json={"service_id": service_two["id"], "duration_minutes_override": 40},
    )
    assert assign.status_code == 201, assign.text

    provider_list = client.get(f"/api/v1/providers/{provider_one['id']}/services", headers=auth_headers)
    assert provider_list.status_code == 200, provider_list.text
    names = {row["name"] for row in provider_list.json()}
    assert names == {service_one["name"], service_two["name"]}
    second_row = next(row for row in provider_list.json() if row["id"] == service_two["id"])
    assert second_row["duration_minutes_override"] == 40
    assert second_row["effective_duration_minutes"] == 40

    service_query = client.get(
        "/api/v1/services",
        headers=auth_headers,
        params={"provider_id": provider_one["id"]},
    )
    assert service_query.status_code == 200, service_query.text
    queried_names = {row["name"] for row in service_query.json()}
    assert queried_names == {service_one["name"], service_two["name"]}


def test_remove_service_assignment(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Remove Assignment Org")
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_one["id"], name="Massage")

    assign = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"]},
    )
    assert assign.status_code == 201, assign.text

    delete_response = client.delete(
        f"/api/v1/providers/{provider_two['id']}/services/{service['id']}",
        headers=auth_headers,
    )
    assert delete_response.status_code == 204
    provider_two_services = client.get(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
    )
    assert provider_two_services.status_code == 200, provider_two_services.text
    assert provider_two_services.json() == []


def test_appointment_rejected_when_provider_cannot_perform_service(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Appointment Capability Org")
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_one["id"], name="Coloring")

    availability = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_two["id"],
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert availability.status_code == 201, availability.text

    customer = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Capability Customer",
            "phone_number": "+14447770001",
            "email": "capability-customer@test.local",
            "preferred_language": "en",
        },
    ).json()

    monday = _next_weekday(0)
    start_dt = f"{monday.isoformat()}T09:00:00+00:00"
    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": org["location_id"],
            "provider_id": provider_two["id"],
            "service_id": service["id"],
            "customer_id": customer["id"],
            "start_datetime": start_dt,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider is not assigned to the selected service."


def test_slot_generation_respects_provider_duration_override(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Duration Override Org")
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider_one["id"],
        name="Therapy Session",
        duration_minutes=30,
    )
    assign = client.post(
        f"/api/v1/providers/{provider_two['id']}/services",
        headers=auth_headers,
        json={"service_id": service["id"], "duration_minutes_override": 45},
    )
    assert assign.status_code == 201, assign.text

    availability = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_two["id"],
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert availability.status_code == 201, availability.text

    monday = _next_weekday(0)
    slots_response = client.get(
        f"/api/v1/scheduling/providers/{provider_two['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": org["location_id"],
        },
    )
    assert slots_response.status_code == 200, slots_response.text
    slots = slots_response.json()
    assert len(slots) == 2
    assert slots[0]["start_datetime"] < slots[1]["start_datetime"]


def test_permissions_admin_provider_staff_for_assignment(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Permission Capability Org")
    admin_user = _create_user(db_session, email="cap-admin@test.local", full_name="Capability Admin")
    staff_user = _create_user(db_session, email="cap-staff@test.local", full_name="Capability Staff")
    provider_user = _create_user(db_session, email="cap-provider@test.local", full_name="Capability Provider")

    _add_member(client, auth_headers, organization_id=org["id"], user_id=admin_user.id, role="admin")
    _add_member(client, auth_headers, organization_id=org["id"], user_id=staff_user.id, role="staff")

    provider_profile = _create_provider(
        client,
        auth_headers,
        organization_id=org["id"],
        display_name="Provider Profile",
        user_id=provider_user.id,
    )
    service_owner = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Service Owner")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=service_owner["id"], name="Peel")

    admin_headers = _auth_headers(client, email=admin_user.email)
    staff_headers = _auth_headers(client, email=staff_user.email)
    provider_headers = _auth_headers(client, email=provider_user.email)

    provider_self_list = client.get(
        f"/api/v1/providers/{provider_profile['id']}/services",
        headers=provider_headers,
    )
    assert provider_self_list.status_code == 200

    provider_other_list = client.get(
        f"/api/v1/providers/{service_owner['id']}/services",
        headers=provider_headers,
    )
    assert provider_other_list.status_code == 403

    provider_assign = client.post(
        f"/api/v1/providers/{provider_profile['id']}/services",
        headers=provider_headers,
        json={"service_id": service["id"]},
    )
    assert provider_assign.status_code == 403

    staff_list = client.get(
        f"/api/v1/providers/{provider_profile['id']}/services",
        headers=staff_headers,
    )
    assert staff_list.status_code == 200

    staff_assign = client.post(
        f"/api/v1/providers/{provider_profile['id']}/services",
        headers=staff_headers,
        json={"service_id": service["id"]},
    )
    assert staff_assign.status_code == 403

    admin_assign = client.post(
        f"/api/v1/providers/{provider_profile['id']}/services",
        headers=admin_headers,
        json={"service_id": service["id"]},
    )
    assert admin_assign.status_code == 201, admin_assign.text
