from fastapi.testclient import TestClient


def test_customer_channel_identity_linking(client: TestClient, auth_headers: dict[str, str]) -> None:
    customer_response = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Identity Customer",
            "phone_number": "+1999000001",
            "email": "identity@test.local",
            "preferred_language": "en",
        },
    )
    customer_id = customer_response.json()["id"]

    link_response = client.post(
        "/api/v1/customer-identities",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "channel": "telegram",
            "external_user_id": "tg-user-123",
            "external_chat_id": "tg-chat-456",
        },
    )
    assert link_response.status_code == 201
    payload = link_response.json()
    assert payload["channel"] == "telegram"

    list_response = client.get(
        "/api/v1/customer-identities",
        headers=auth_headers,
        params={"customer_id": customer_id},
    )
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    duplicate_channel_response = client.post(
        "/api/v1/customer-identities",
        headers=auth_headers,
        json={
            "customer_id": customer_id,
            "channel": "telegram",
            "external_user_id": "tg-user-999",
            "external_chat_id": "tg-chat-999",
        },
    )
    assert duplicate_channel_response.status_code == 409

    second_customer_response = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Identity Customer 2",
            "phone_number": "+1999000002",
            "email": "identity2@test.local",
            "preferred_language": "en",
        },
    )
    second_customer_id = second_customer_response.json()["id"]

    duplicate_external_user_response = client.post(
        "/api/v1/customer-identities",
        headers=auth_headers,
        json={
            "customer_id": second_customer_id,
            "channel": "telegram",
            "external_user_id": "tg-user-123",
            "external_chat_id": "tg-chat-777",
        },
    )
    assert duplicate_external_user_response.status_code == 409
