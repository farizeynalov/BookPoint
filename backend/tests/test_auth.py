from fastapi.testclient import TestClient


def test_login_and_me(client: TestClient, auth_headers: dict[str, str]) -> None:
    me_response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me_response.status_code == 200
    payload = me_response.json()
    assert payload["email"] == "owner@test.local"
    assert payload["is_active"] is True
