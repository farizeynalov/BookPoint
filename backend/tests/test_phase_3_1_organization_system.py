from datetime import date, datetime, timedelta

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


def _auth_headers(client: TestClient, *, email: str, password: str = "password123") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
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
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    payload["location_id"] = _get_default_location_id(client, headers, payload["id"])
    return payload


def _create_provider(client: TestClient, headers: dict[str, str], *, organization_id: int, display_name: str = "Provider One") -> dict:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
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
    headers: dict[str, str],
    *,
    organization_id: int,
    provider_id: int,
    name: str = "Service One",
) -> dict:
    response = client.post(
        "/api/v1/services",
        headers=headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": name,
            "duration_minutes": 30,
            "price": "25.00",
            "description": None,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_organization(client: TestClient, auth_headers: dict[str, str]) -> None:
    created = _create_org(client, auth_headers, name="Downtown Clinic")
    assert created["name"] == "Downtown Clinic"
    assert created["slug"] == "downtown-clinic"


def test_slug_uniqueness(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = _create_org(client, auth_headers, name="Downtown Clinic")
    second = _create_org(client, auth_headers, name="Downtown Clinic")
    assert first["slug"] == "downtown-clinic"
    assert second["slug"].startswith("downtown-clinic")
    assert second["slug"] != first["slug"]


def test_add_organization_member(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Member Org")
    member_user = _create_user(db_session, email="member@test.local", full_name="Member User")

    response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=auth_headers,
        json={"user_id": member_user.id, "role": "staff"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["organization_id"] == org["id"]
    assert payload["user_id"] == member_user.id
    assert payload["role"] == "staff"


def test_role_assignment_update(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Roles Org")
    member_user = _create_user(db_session, email="role@test.local", full_name="Role User")
    created = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=auth_headers,
        json={"user_id": member_user.id, "role": "staff"},
    )
    assert created.status_code == 201, created.text
    member_id = created.json()["id"]

    update_response = client.patch(
        f"/api/v1/organizations/{org['id']}/members/{member_id}",
        headers=auth_headers,
        json={"role": "provider"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["role"] == "provider"


def test_provider_must_belong_to_creator_organization(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    other_user = _create_user(db_session, email="other-owner@test.local", full_name="Other Owner")
    other_headers = _auth_headers(client, email=other_user.email)
    foreign_org = _create_org(client, other_headers, name="Foreign Org")

    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": foreign_org["id"],
            "display_name": "No Access Provider",
            "appointment_duration_minutes": 30,
            "is_active": True,
            "user_id": None,
            "title": None,
            "bio": None,
        },
    )
    assert response.status_code == 403


def test_service_must_belong_to_organization(client: TestClient, auth_headers: dict[str, str]) -> None:
    org_one = _create_org(client, auth_headers, name="Org One")
    org_two = _create_org(client, auth_headers, name="Org Two")
    provider_two = _create_provider(client, auth_headers, organization_id=org_two["id"], display_name="Org Two Provider")

    response = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": org_one["id"],
            "provider_id": provider_two["id"],
            "name": "Cross Org Service",
            "duration_minutes": 30,
            "price": "15.00",
            "description": None,
            "is_active": True,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Provider org mismatch"


def test_appointment_cannot_mix_organizations(client: TestClient, auth_headers: dict[str, str]) -> None:
    org_one = _create_org(client, auth_headers, name="Appointments Org One")
    org_two = _create_org(client, auth_headers, name="Appointments Org Two")
    provider_one = _create_provider(client, auth_headers, organization_id=org_one["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org_two["id"], display_name="Provider Two")
    service_one = _create_service(
        client,
        auth_headers,
        organization_id=org_one["id"],
        provider_id=provider_one["id"],
        name="Service One",
    )
    service_two = _create_service(
        client,
        auth_headers,
        organization_id=org_two["id"],
        provider_id=provider_two["id"],
        name="Service Two",
    )
    assert service_one["organization_id"] != service_two["organization_id"]

    availability_response = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_one["id"],
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert availability_response.status_code == 201, availability_response.text

    customer = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Appointment Customer",
            "phone_number": "+14445550001",
            "email": "appointment-customer@test.local",
            "preferred_language": "en",
        },
    ).json()

    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{provider_one['id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service_one["id"],
            "location_id": org_one["location_id"],
        },
    ).json()
    start_datetime = datetime.fromisoformat(slots[0]["start_datetime"])

    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "location_id": org_one["location_id"],
            "provider_id": provider_one["id"],
            "service_id": service_two["id"],
            "customer_id": customer["id"],
            "start_datetime": start_datetime.isoformat(),
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 400
    assert "organization mismatch" in response.json()["detail"]


def test_organization_membership_uniqueness(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Unique Membership Org")
    member_user = _create_user(db_session, email="unique-member@test.local", full_name="Unique Member")

    first = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=auth_headers,
        json={"user_id": member_user.id, "role": "staff"},
    )
    second = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=auth_headers,
        json={"user_id": member_user.id, "role": "provider"},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    members_response = client.get(f"/api/v1/organizations/{org['id']}/members", headers=auth_headers)
    assert members_response.status_code == 200, members_response.text
    memberships = [row for row in members_response.json() if row["user_id"] == member_user.id]
    assert len(memberships) == 1
    assert memberships[0]["role"] == "provider"


def test_permission_enforcement_staff_cannot_manage_org_but_can_create_appointments(
    client: TestClient,
    auth_headers: dict[str, str],
    db_session: Session,
) -> None:
    org = _create_org(client, auth_headers, name="Permission Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Permission Provider")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name="Permission Service",
    )
    availability_response = client.post(
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
    assert availability_response.status_code == 201, availability_response.text

    customer = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Permission Customer",
            "phone_number": "+14445550002",
            "email": "permission-customer@test.local",
            "preferred_language": "en",
        },
    ).json()

    staff_user = _create_user(db_session, email="staff@test.local", full_name="Staff User")
    member_response = client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=auth_headers,
        json={"user_id": staff_user.id, "role": "staff"},
    )
    assert member_response.status_code == 201, member_response.text
    staff_headers = _auth_headers(client, email=staff_user.email)

    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{provider['id']}/slots",
        headers=staff_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": service["id"],
            "location_id": org["location_id"],
        },
    ).json()
    start_datetime = slots[0]["start_datetime"]

    create_appointment_response = client.post(
        "/api/v1/appointments",
        headers=staff_headers,
        json={
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
    assert create_appointment_response.status_code == 201, create_appointment_response.text

    org_update_response = client.patch(
        f"/api/v1/organizations/{org['id']}",
        headers=staff_headers,
        json={"name": "Permission Org Updated"},
    )
    assert org_update_response.status_code == 403

    provider_create_response = client.post(
        "/api/v1/providers",
        headers=staff_headers,
        json={
            "organization_id": org["id"],
            "display_name": "Blocked Provider",
            "appointment_duration_minutes": 30,
            "is_active": True,
            "user_id": None,
            "title": None,
            "bio": None,
        },
    )
    assert provider_create_response.status_code == 403
