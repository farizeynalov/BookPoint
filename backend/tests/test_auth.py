from fastapi.testclient import TestClient

from app.models.user import User


def test_login_success_returns_token_payload(client: TestClient, seeded_user: User) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user.email, "password": "password123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload
    assert payload["token_type"] == "bearer"


def test_login_invalid_password_returns_401(client: TestClient, seeded_user: User) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_auth_me_works_with_returned_bearer_token(client: TestClient, seeded_user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user.email, "password": "password123"},
    )
    token = login_response.json()["access_token"]
    me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["email"] == seeded_user.email
    assert payload["is_active"] is True
