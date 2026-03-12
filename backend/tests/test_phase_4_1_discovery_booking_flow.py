from datetime import date, timedelta

from fastapi.testclient import TestClient


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _create_org(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    name: str,
    is_active: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": name,
            "business_type": "clinic",
            "city": "Baku",
            "address": "Main",
            "timezone": "Asia/Baku",
            "is_active": is_active,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _get_default_location_id(client: TestClient, auth_headers: dict[str, str], organization_id: int) -> int:
    response = client.get(f"/api/v1/organizations/{organization_id}/locations", headers=auth_headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["id"]


def _create_location(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    organization_id: int,
    name: str,
) -> dict:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/locations",
        headers=auth_headers,
        json={"name": name, "city": "Baku", "timezone": "Asia/Baku", "is_active": True},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_provider(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    organization_id: int,
    display_name: str,
) -> dict:
    response = client.post(
        "/api/v1/providers",
        headers=auth_headers,
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
    auth_headers: dict[str, str],
    *,
    organization_id: int,
    provider_id: int,
    name: str,
) -> dict:
    response = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": organization_id,
            "provider_id": provider_id,
            "name": name,
            "description": None,
            "duration_minutes": 30,
            "price": "25.00",
            "currency": "USD",
            "buffer_before_minutes": 0,
            "buffer_after_minutes": 0,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_customer(
    client: TestClient,
    auth_headers: dict[str, str],
    *,
    full_name: str,
    phone_number: str,
    email: str | None,
) -> dict:
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": full_name,
            "phone_number": phone_number,
            "email": email,
            "preferred_language": "en",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_availability(client: TestClient, auth_headers: dict[str, str], *, provider_id: int) -> None:
    response = client.post(
        "/api/v1/provider-availability",
        headers=auth_headers,
        json={
            "provider_id": provider_id,
            "weekday": 0,
            "start_time": "09:00:00",
            "end_time": "11:00:00",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text


def _first_discovery_slot(
    client: TestClient,
    *,
    provider_id: int,
    service_id: int,
    location_id: int,
    query_date: date,
) -> str:
    response = client.get(
        f"/api/v1/discovery/providers/{provider_id}/slots",
        params={
            "service_id": service_id,
            "location_id": location_id,
            "date": query_date.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload
    return payload[0]["start_datetime"]


def _create_discovery_booking(
    client: TestClient,
    *,
    organization_id: int,
    location_id: int,
    provider_id: int,
    service_id: int,
    scheduled_start: str,
    customer_name: str,
    customer_phone: str,
    customer_email: str | None,
):
    return client.post(
        "/api/v1/discovery/bookings",
        json={
            "organization_id": organization_id,
            "location_id": location_id,
            "provider_id": provider_id,
            "service_id": service_id,
            "scheduled_start": scheduled_start,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "customer_email": customer_email,
            "preferred_language": "en",
        },
    )


def test_discovery_list_organizations(client: TestClient, auth_headers: dict[str, str]) -> None:
    active_org = _create_org(client, auth_headers, name="Discovery Active Org", is_active=True)
    _create_org(client, auth_headers, name="Discovery Inactive Org", is_active=False)

    response = client.get("/api/v1/discovery/organizations")
    assert response.status_code == 200, response.text
    org_ids = {row["id"] for row in response.json()}
    assert active_org["id"] in org_ids


def test_discovery_list_locations_for_organization(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Locations Org")
    location = _create_location(client, auth_headers, organization_id=org["id"], name="Airport Branch")

    response = client.get(f"/api/v1/discovery/organizations/{org['id']}/locations")
    assert response.status_code == 200, response.text
    location_ids = {row["id"] for row in response.json()}
    assert location["id"] in location_ids


def test_discovery_list_services_for_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Services Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(
        client,
        auth_headers,
        organization_id=org["id"],
        provider_id=provider["id"],
        name="Dental Cleaning",
    )

    response = client.get(f"/api/v1/discovery/locations/{location_id}/services")
    assert response.status_code == 200, response.text
    service_ids = {row["id"] for row in response.json()}
    assert service["id"] in service_ids


def test_discovery_list_providers_for_service_at_location(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Providers Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="X-Ray")

    response = client.get(f"/api/v1/discovery/locations/{location_id}/services/{service['id']}/providers")
    assert response.status_code == 200, response.text
    provider_ids = {row["id"] for row in response.json()}
    assert provider["id"] in provider_ids


def test_inactive_location_service_provider_hidden_from_discovery(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Visibility Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    hidden_location = _create_location(client, auth_headers, organization_id=org["id"], name="Hidden Branch")

    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Therapy")

    deactivate_location = client.delete(
        f"/api/v1/organizations/{org['id']}/locations/{hidden_location['id']}",
        headers=auth_headers,
    )
    assert deactivate_location.status_code == 204

    deactivate_provider = client.post(f"/api/v1/providers/{provider['id']}/deactivate", headers=auth_headers)
    assert deactivate_provider.status_code == 200

    providers_hidden_response = client.get(f"/api/v1/discovery/locations/{location_id}/services/{service['id']}/providers")
    assert providers_hidden_response.status_code == 200
    assert providers_hidden_response.json() == []

    deactivate_service = client.post(f"/api/v1/services/{service['id']}/deactivate", headers=auth_headers)
    assert deactivate_service.status_code == 200

    locations_response = client.get(f"/api/v1/discovery/organizations/{org['id']}/locations")
    assert locations_response.status_code == 200
    location_ids = {row["id"] for row in locations_response.json()}
    assert hidden_location["id"] not in location_ids

    services_response = client.get(f"/api/v1/discovery/locations/{location_id}/services")
    assert services_response.status_code == 200
    assert services_response.json() == []

    providers_after_service_hidden = client.get(f"/api/v1/discovery/locations/{location_id}/services/{service['id']}/providers")
    assert providers_after_service_hidden.status_code == 404


def test_provider_not_assigned_to_service_is_excluded(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Provider-Service Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider_one = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider One")
    provider_two = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider Two")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider_one["id"], name="Service One")

    response = client.get(f"/api/v1/discovery/locations/{location_id}/services/{service['id']}/providers")
    assert response.status_code == 200, response.text
    provider_ids = {row["id"] for row in response.json()}
    assert provider_one["id"] in provider_ids
    assert provider_two["id"] not in provider_ids


def test_provider_not_assigned_to_location_is_excluded(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Provider-Location Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Remote Branch")

    assign_service_location = client.post(
        f"/api/v1/services/{service['id']}/locations",
        headers=auth_headers,
        json={"location_id": second_location["id"]},
    )
    assert assign_service_location.status_code == 201, assign_service_location.text

    response = client.get(f"/api/v1/discovery/locations/{second_location['id']}/services/{service['id']}/providers")
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_slot_discovery_validates_provider_service_location_combination(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    org = _create_org(client, auth_headers, name="Discovery Slot Validation Org")
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    second_location = _create_location(client, auth_headers, organization_id=org["id"], name="Remote Branch")
    _add_availability(client, auth_headers, provider_id=provider["id"])

    monday = _next_weekday(0)
    response = client.get(
        f"/api/v1/discovery/providers/{provider['id']}/slots",
        params={
            "service_id": service["id"],
            "location_id": second_location["id"],
            "date": monday.isoformat(),
        },
    )
    assert response.status_code == 400


def test_booking_flow_creates_new_customer_when_none_exists(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Booking New Customer Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_availability(client, auth_headers, provider_id=provider["id"])

    monday = _next_weekday(0)
    slot_start = _first_discovery_slot(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=monday,
    )

    response = _create_discovery_booking(
        client,
        organization_id=org["id"],
        location_id=location_id,
        provider_id=provider["id"],
        service_id=service["id"],
        scheduled_start=slot_start,
        customer_name="Discovery Customer",
        customer_phone="+1 555 000 1001",
        customer_email="newcustomer@test.local",
    )
    assert response.status_code == 201, response.text

    customers = client.get("/api/v1/customers", headers=auth_headers)
    assert customers.status_code == 200, customers.text
    assert len(customers.json()) == 1


def test_booking_flow_reuses_existing_customer_when_contact_matches_same_organization(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    org = _create_org(client, auth_headers, name="Discovery Booking Reuse Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_availability(client, auth_headers, provider_id=provider["id"])

    existing_customer = _create_customer(
        client,
        auth_headers,
        full_name="Existing Customer",
        phone_number="+15550002002",
        email="existing@test.local",
    )

    monday = _next_weekday(0)
    slot_start = _first_discovery_slot(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=monday,
    )

    response = _create_discovery_booking(
        client,
        organization_id=org["id"],
        location_id=location_id,
        provider_id=provider["id"],
        service_id=service["id"],
        scheduled_start=slot_start,
        customer_name="Existing Customer Updated",
        customer_phone="+1 (555) 000-2002",
        customer_email="EXISTING@test.local",
    )
    assert response.status_code == 201, response.text
    assert response.json()["customer_id"] == existing_customer["id"]


def test_booking_flow_rejects_unavailable_slot(client: TestClient, auth_headers: dict[str, str]) -> None:
    org = _create_org(client, auth_headers, name="Discovery Booking Conflict Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_availability(client, auth_headers, provider_id=provider["id"])

    monday = _next_weekday(0)
    slot_start = _first_discovery_slot(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=monday,
    )

    first = _create_discovery_booking(
        client,
        organization_id=org["id"],
        location_id=location_id,
        provider_id=provider["id"],
        service_id=service["id"],
        scheduled_start=slot_start,
        customer_name="First Customer",
        customer_phone="+15550003003",
        customer_email="first@test.local",
    )
    assert first.status_code == 201, first.text

    second = _create_discovery_booking(
        client,
        organization_id=org["id"],
        location_id=location_id,
        provider_id=provider["id"],
        service_id=service["id"],
        scheduled_start=slot_start,
        customer_name="Second Customer",
        customer_phone="+15550003004",
        customer_email="second@test.local",
    )
    assert second.status_code == 400


def test_booking_flow_triggers_notification_pipeline_hook(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    org = _create_org(client, auth_headers, name="Discovery Booking Notification Org")
    location_id = _get_default_location_id(client, auth_headers, org["id"])
    provider = _create_provider(client, auth_headers, organization_id=org["id"], display_name="Provider A")
    service = _create_service(client, auth_headers, organization_id=org["id"], provider_id=provider["id"], name="Service A")
    _add_availability(client, auth_headers, provider_id=provider["id"])

    monday = _next_weekday(0)
    slot_start = _first_discovery_slot(
        client,
        provider_id=provider["id"],
        service_id=service["id"],
        location_id=location_id,
        query_date=monday,
    )

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_created_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    booking_response = _create_discovery_booking(
        client,
        organization_id=org["id"],
        location_id=location_id,
        provider_id=provider["id"],
        service_id=service["id"],
        scheduled_start=slot_start,
        customer_name="Notify Customer",
        customer_phone="+15550004005",
        customer_email="notify@test.local",
    )
    assert booking_response.status_code == 201, booking_response.text
    assert captured == [booking_response.json()["appointment_id"]]


def test_existing_admin_endpoints_remain_protected_while_discovery_is_public(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    org = _create_org(client, auth_headers, name="Discovery Access Guard Org")

    protected = client.get("/api/v1/providers")
    assert protected.status_code == 401

    discovery = client.get("/api/v1/discovery/organizations")
    assert discovery.status_code == 200
    org_ids = {row["id"] for row in discovery.json()}
    assert org["id"] in org_ids
