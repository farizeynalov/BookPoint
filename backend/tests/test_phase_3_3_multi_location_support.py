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


def _create_org(client: TestClient, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/organizations",
        headers=headers,
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
    name: str,
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
            "price": "30.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_customer(client: TestClient, headers: dict[str, str], *, suffix: str) -> dict:
    response = client.post(
        "/api/v1/customers",
        headers=headers,
        json={
            "full_name": f"Customer {suffix}",
            "phone_number": f"+1555000{suffix}",
            "email": f"customer-{suffix}@test.local",
            "preferred_language": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_location(client: TestClient, headers: dict[str, str], *, organization_id: int, name: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/locations",
        headers=headers,
        json={
            "name": name,
            "address_line_1": "Street 1",
            "city": "Baku",
            "region": "Baku",
            "postal_code": "AZ1000",
            "country": "AZ",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_weekly_availability(client: TestClient, headers: dict[str, str], *, provider_id: int) -> None:
    response = client.post(
        "/api/v1/provider-availability",
        headers=headers,
        json={
            "provider_id": provider_id,
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text


def _add_member(client: TestClient, headers: dict[str, str], *, organization_id: int, user_id: int, role: str) -> None:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers=headers,
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201, response.text


def test_create_organization_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Location CRUD Org")
    created = _create_location(client, auth_headers, organization_id=org["id"], name="Airport Branch")
    assert created["organization_id"] == org["id"]
    assert created["name"] == "Airport Branch"


def test_location_slug_uniqueness_within_organization(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Location Slug Org")
    first = _create_location(client, auth_headers, organization_id=org["id"], name="Downtown Branch")
    second = _create_location(client, auth_headers, organization_id=org["id"], name="Downtown Branch")
    assert first["slug"] == "downtown-branch"
    assert second["slug"].startswith("downtown-branch")
    assert second["slug"] != first["slug"]


def test_assign_provider_to_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Provider Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Second Branch")

    assign = client.post(
        f"/api/v1/providers/{provider['id']}/locations",
        headers=auth_headers,
        json={"location_id": second_location["id"]},
    )
    assert assign.status_code == 201, assign.text
    listed = client.get(f"/api/v1/providers/{provider['id']}/locations", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    location_ids = {row["id"] for row in listed.json()}
    assert second_location["id"] in location_ids


def test_assign_service_to_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Service Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name="Cleaning",
    )
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Second Branch")

    assign = client.post(
        f"/api/v1/services/{service['id']}/locations",
        headers=auth_headers,
        json={"location_id": second_location["id"]},
    )
    assert assign.status_code == 201, assign.text
    listed = client.get(f"/api/v1/services/{service['id']}/locations", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    location_ids = {row["id"] for row in listed.json()}
    assert second_location["id"] in location_ids


def test_provider_location_org_mismatch_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    org_one = _create_org(client, auth_headers, name="Provider Org One")
    org_two = _create_org(client, auth_headers, name="Provider Org Two")
    provider = _create_provider(client, auth_headers, organization_id=org_one["id"], display_name="Provider A")

    response = client.post(
        f"/api/v1/providers/{provider['id']}/locations",
        headers=auth_headers,
        json={"location_id": org_two["location_id"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider and location organization mismatch"


def test_service_location_org_mismatch_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    org_one = _create_org(client, auth_headers, name="Service Org One")
    org_two = _create_org(client, auth_headers, name="Service Org Two")
    provider = _create_provider(client, auth_headers, organization_id=org_one["id"], display_name="Provider A")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org_one["id"],
        provider_id=provider["id"],
        name="Service A",
    )

    response = client.post(
        f"/api/v1/services/{service['id']}/locations",
        headers=auth_headers,
        json={"location_id": org_two["location_id"]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Service and location organization mismatch"


def test_appointment_creation_requires_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Appointment Location Required Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_weekly_availability(client, auth_headers, provider_id=provider["id"])
    customer = _create_customer(client, auth_headers, suffix="3301")

    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{provider['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": org["location_id"],
        },
    )
    assert slots.status_code == 200, slots.text
    start_datetime = slots.json()[0]["start_datetime"]

    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "provider_id": provider["id"],
            "service_id": service["id"],
            "customer_id": customer["id"],
            "start_datetime": start_datetime,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 422


def test_appointment_rejected_if_provider_not_at_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Provider Not At Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Remote Branch")
    customer = _create_customer(client, auth_headers, suffix="3302")

    monday = _next_weekday(0)
    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": second_location["id"],
            "provider_id": provider["id"],
            "service_id": service["id"],
            "customer_id": customer["id"],
            "start_datetime": f"{monday.isoformat()}T09:00:00+00:00",
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider is not assigned to the selected location."


def test_appointment_rejected_if_service_not_at_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Service Not At Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Remote Branch")
    customer = _create_customer(client, auth_headers, suffix="3303")

    assign_provider = client.post(
        f"/api/v1/providers/{provider['id']}/locations",
        headers=auth_headers,
        json={"location_id": second_location["id"]},
    )
    assert assign_provider.status_code == 201, assign_provider.text

    monday = _next_weekday(0)
    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": second_location["id"],
            "provider_id": provider["id"],
            "service_id": service["id"],
            "customer_id": customer["id"],
            "start_datetime": f"{monday.isoformat()}T09:00:00+00:00",
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Service is not available at the selected location."


def test_slot_generation_requires_valid_provider_service_location_combination(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    org = _create_org(client, auth_headers, name="Slot Combination Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Remote Branch")

    monday = _next_weekday(0)
    response = client.get(
        f"/api/v1/scheduling/providers/{provider['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": second_location["id"],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider is not assigned to the selected location."


def test_slot_generation_works_for_valid_location_combination(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Valid Slot Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_weekly_availability(client, auth_headers, provider_id=provider["id"])

    monday = _next_weekday(0)
    response = client.get(
        f"/api/v1/scheduling/providers/{provider['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": org["location_id"],
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) > 0


def test_permission_enforcement_for_location_management(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Location Permission Org")
    admin_user = _create_user(db_session, email="loc-admin@test.local", full_name="Loc Admin")
    staff_user = _create_user(db_session, email="loc-staff@test.local", full_name="Loc Staff")
    provider_user = _create_user(db_session, email="loc-provider@test.local", full_name="Loc Provider")

    _add_member(client, auth_headers, organization_id=org["id"], user_id=admin_user.id, role="admin")
    _add_member(client, auth_headers, organization_id=org["id"], user_id=staff_user.id, role="staff")

    provider_profile = _create_provider(
        client,
        auth_headers,
        organization_id=org["id"],
        display_name="Provider Profile",
        user_id=provider_user.id,
    )

    admin_headers = _auth_headers(client, email=admin_user.email)
    staff_headers = _auth_headers(client, email=staff_user.email)
    provider_headers = _auth_headers(client, email=provider_user.email)

    provider_list = client.get(f"/api/v1/providers/{provider_profile['id']}/locations", headers=provider_headers)
    assert provider_list.status_code == 200

    staff_list = client.get(f"/api/v1/organizations/{org['id']}/locations", headers=staff_headers)
    assert staff_list.status_code == 200

    provider_create = client.post(
        f"/api/v1/organizations/{org['id']}/locations",
        headers=provider_headers,
        json={"name": "Provider Branch"},
    )
    assert provider_create.status_code == 403

    staff_create = client.post(
        f"/api/v1/organizations/{org['id']}/locations",
        headers=staff_headers,
        json={"name": "Staff Branch"},
    )
    assert staff_create.status_code == 403

    admin_create = client.post(
        f"/api/v1/organizations/{org['id']}/locations",
        headers=admin_headers,
        json={"name": "Admin Branch"},
    )
    assert admin_create.status_code == 201, admin_create.text


def test_default_location_backfill_strategy_keeps_existing_flow_stable(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    org = _create_org(client, auth_headers, name="Legacy Flow Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_weekly_availability(client, auth_headers, provider_id=provider["id"])
    customer = _create_customer(client, auth_headers, suffix="3304")

    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{provider['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": org["location_id"],
        },
    )
    assert slots.status_code == 200, slots.text
    start_datetime = slots.json()[0]["start_datetime"]

    appointment = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "organization_id": org["id"],
            "location_id": org["location_id"],
            "provider_id": provider["id"],
            "service_id": service["id"],
            "customer_id": customer["id"],
            "start_datetime": start_datetime,
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert appointment.status_code == 201, appointment.text
    assert appointment.json()["location_id"] == org["location_id"]
