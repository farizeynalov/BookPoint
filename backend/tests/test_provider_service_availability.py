from fastapi.testclient import TestClient

from app.models.user import User


def _create_org(client: TestClient, auth_headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Provider Org",
            "business_type": "salon",
            "city": "Baku",
            "address": "Main 1",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    )
    return response.json()["id"]


def _create_provider(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": None,
            "display_name": "Provider One",
            "title": "Barber",
            "bio": "Bio",
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    return response.json()["id"]


def test_provider_creation(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": None,
            "display_name": "Provider Test",
            "title": "Therapist",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["display_name"] == "Provider Test"


def test_service_creation(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    response = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": "Haircut 30",
            "description": None,
            "duration_minutes": 30,
            "price": "25.00",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Haircut 30"


def test_availability_creation(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    response = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "12:00:00",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["weekday"] == 0


def test_availability_overlap_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    first = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": 1,
            "start_time": "09:00:00",
            "end_time": "12:00:00",
            "is_active": True,
        },
    )
    assert first.status_code == 201

    overlap = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": 1,
            "start_time": "11:00:00",
            "end_time": "13:00:00",
            "is_active": True,
        },
    )
    assert overlap.status_code == 400
    assert "Overlapping availability block" in overlap.json()["detail"]


def test_provider_and_service_duration_validation(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    bad_provider = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": None,
            "display_name": "Invalid Duration",
            "title": "Staff",
            "bio": None,
            "appointment_duration_minutes": 0,
            "is_active": True,
        },
    )
    assert bad_provider.status_code == 422

    provider_id = _create_provider(client, auth_headers, organization_id)
    bad_service = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": "Invalid Service",
            "description": None,
            "duration_minutes": -10,
            "price": "-1.00",
            "is_active": True,
        },
    )
    assert bad_service.status_code == 422


def test_provider_user_link_must_be_unique(
    client: TestClient,
    auth_headers: dict[str, str],
    seeded_user: User,
) -> None:
    organization_id = _create_org(client, auth_headers)
    first = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": seeded_user.id,
            "display_name": "Provider User Link 1",
            "title": None,
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": seeded_user.id,
            "display_name": "Provider User Link 2",
            "title": None,
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    assert second.status_code == 409
