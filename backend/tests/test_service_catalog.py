from fastapi.testclient import TestClient


def _create_org(client: TestClient, auth_headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Service Catalog Org",
            "business_type": "salon",
            "city": "Baku",
            "address": "Main 10",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_provider(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "user_id": None,
            "display_name": "Provider Catalog",
            "title": "Stylist",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_create_provider_service_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Haircut",
            "description": "Basic haircut",
            "duration_minutes": 45,
            "price": "30.00",
            "currency": "USD",
            "buffer_before_minutes": 5,
            "buffer_after_minutes": 10,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["provider_id"] == provider_id
    assert payload["organization_id"] == organization_id
    assert payload["name"] == "Haircut"
    assert payload["buffer_before_minutes"] == 5
    assert payload["buffer_after_minutes"] == 10


def test_create_service_nonexistent_provider(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/providers/9999/services",
        headers=auth_headers,
        json={
            "name": "Consultation",
            "description": None,
            "duration_minutes": 30,
            "price": "40.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 404


def test_create_service_invalid_duration_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Invalid Duration",
            "description": None,
            "duration_minutes": 0,
            "price": "10.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 422


def test_create_service_negative_buffer_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Invalid Buffer",
            "description": None,
            "duration_minutes": 30,
            "price": "10.00",
            "currency": "USD",
            "buffer_before_minutes": -1,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 422


def test_list_provider_services_active_default(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    active_response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Active Service",
            "description": None,
            "duration_minutes": 30,
            "price": "10.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert active_response.status_code == 201

    inactive_response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Inactive Service",
            "description": None,
            "duration_minutes": 30,
            "price": "10.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": False,
        },
    )
    assert inactive_response.status_code == 201

    list_response = client.get(f"/api/v1/providers/{provider_id}/services", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["name"] == "Active Service"

    list_with_inactive_response = client.get(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        params={"include_inactive": True},
    )
    assert list_with_inactive_response.status_code == 200
    assert len(list_with_inactive_response.json()) == 2


def test_get_patch_and_deactivate_service(client: TestClient, auth_headers: dict[str, str]) -> None:
    organization_id = _create_org(client, auth_headers)
    provider_id = _create_provider(client, auth_headers, organization_id)
    create_response = client.post(
        f"/api/v1/providers/{provider_id}/services",
        headers=auth_headers,
        json={
            "name": "Therapy",
            "description": "Initial",
            "duration_minutes": 60,
            "price": "70.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert create_response.status_code == 201
    service_id = create_response.json()["id"]

    get_response = client.get(f"/api/v1/services/{service_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Therapy"

    patch_response = client.patch(
        f"/api/v1/services/{service_id}",
        headers=auth_headers,
        json={
            "name": "Therapy Updated",
            "buffer_after_minutes": 15,
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Therapy Updated"
    assert patch_response.json()["buffer_after_minutes"] == 15

    delete_response = client.delete(f"/api/v1/services/{service_id}", headers=auth_headers)
    assert delete_response.status_code == 200
    assert delete_response.json()["is_active"] is False
