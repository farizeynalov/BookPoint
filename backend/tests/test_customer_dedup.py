from fastapi.testclient import TestClient


def test_duplicate_customer_phone_normalized_rejected(client: TestClient, auth_headers: dict[str, str]) -> None:
    first = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Phone One",
            "phone_number": "+1 (999) 000-0001",
            "email": "phone1@test.local",
            "preferred_language": "en",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Phone Two",
            "phone_number": "+19990000001",
            "email": "phone2@test.local",
            "preferred_language": "en",
        },
    )
    assert second.status_code == 409
    assert "phone already exists" in second.json()["detail"]
