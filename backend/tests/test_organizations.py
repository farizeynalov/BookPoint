from fastapi.testclient import TestClient


def test_create_organization(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Test Clinic",
            "business_type": "clinic",
            "city": "Baku",
            "address": "Street 1",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Test Clinic"

    list_response = client.get("/api/v1/organizations", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
