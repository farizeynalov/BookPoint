from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.enums import AppointmentStatus, BookingChannel, NotificationStatus, NotificationType
from app.models.notification import Notification
from app.models.organization import Organization
from app.models.provider import Provider
from app.utils.phone import normalize_phone_number
from app.workers import tasks as worker_tasks


def _next_weekday(target_weekday: int) -> date:
    today = date.today()
    delta = (target_weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _bootstrap_provider_setup(client: TestClient, auth_headers: dict[str, str]) -> dict[str, int]:
    org = client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={
            "name": "Notifications Org",
            "business_type": "clinic",
            "city": "Baku",
            "address": "Main",
            "timezone": "Asia/Baku",
            "is_active": True,
        },
    ).json()
    provider = client.post(
        "/api/v1/providers",
        headers=auth_headers,
        json={
            "organization_id": org["id"],
            "user_id": None,
            "display_name": "Notifications Provider",
            "title": "Doctor",
            "bio": None,
            "appointment_duration_minutes": 30,
            "is_active": True,
        },
    ).json()
    service = client.post(
        "/api/v1/services",
        headers=auth_headers,
        json={
            "organization_id": org["id"],
            "provider_id": provider["id"],
            "name": "Consultation",
            "description": None,
            "duration_minutes": 30,
            "price": "40.00",
            "is_active": True,
        },
    ).json()
    client.post(
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
    customer = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "full_name": "Notification Customer",
            "phone_number": "+1000000401",
            "email": "notification-customer@test.local",
            "preferred_language": "en",
        },
    ).json()
    return {
        "organization_id": org["id"],
        "provider_id": provider["id"],
        "service_id": service["id"],
        "customer_id": customer["id"],
    }


def _create_upcoming_appointment(
    db_session: Session,
    *,
    minutes_from_now: int,
    status: AppointmentStatus = AppointmentStatus.CONFIRMED,
) -> Appointment:
    token = int(datetime.now(timezone.utc).timestamp() * 1_000_000)
    phone = f"+1999{token % 10_000_000:07d}"
    organization = Organization(
        name=f"Notif Org {token}",
        business_type="clinic",
        city="Baku",
        address="Main",
        timezone="Asia/Baku",
        is_active=True,
    )
    provider = Provider(
        organization=organization,
        display_name=f"Notif Provider {token}",
        appointment_duration_minutes=30,
        is_active=True,
    )
    customer = Customer(
        full_name=f"Notif Customer {token}",
        phone_number=phone,
        phone_number_normalized=normalize_phone_number(phone),
        email=f"notif-{token}@test.local",
        preferred_language="en",
    )
    start_datetime = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    end_datetime = start_datetime + timedelta(minutes=30)
    appointment = Appointment(
        organization=organization,
        provider=provider,
        customer=customer,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        status=status,
        booking_channel=BookingChannel.WEB,
        notes="notification-test",
    )
    db_session.add(appointment)
    db_session.commit()
    db_session.refresh(appointment)
    return appointment


def test_appointment_creation_triggers_notification_task(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
        },
    ).json()

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_created_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    response = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_id"],
            "start_datetime": slots[0]["start_datetime"],
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    )
    assert response.status_code == 201
    assert captured == [response.json()["id"]]


def test_appointment_cancellation_triggers_notification_task(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
        },
    ).json()
    created = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_id"],
            "start_datetime": slots[0]["start_datetime"],
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    ).json()

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_cancelled_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    response = client.post(
        f"/api/v1/appointments/{created['id']}/cancel",
        headers=auth_headers,
        json={"notes": "cancelled"},
    )
    assert response.status_code == 200
    assert captured == [created["id"]]


def test_appointment_reschedule_triggers_notification_task(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    data = _bootstrap_provider_setup(client, auth_headers)
    monday = _next_weekday(0)
    slots = client.get(
        f"/api/v1/scheduling/providers/{data['provider_id']}/slots",
        headers=auth_headers,
        params={
            "start_date": monday.isoformat(),
            "end_date": monday.isoformat(),
            "service_id": data["service_id"],
        },
    ).json()
    created = client.post(
        "/api/v1/appointments",
        headers=auth_headers,
        json={
            "provider_id": data["provider_id"],
            "service_id": data["service_id"],
            "customer_id": data["customer_id"],
            "start_datetime": slots[0]["start_datetime"],
            "status": "confirmed",
            "booking_channel": "web",
            "notes": None,
        },
    ).json()

    captured: list[int] = []
    monkeypatch.setattr(
        "app.services.appointment_service.enqueue_appointment_rescheduled_notification",
        lambda appointment_id: captured.append(appointment_id),
    )

    response = client.post(
        f"/api/v1/appointments/{created['id']}/reschedule",
        headers=auth_headers,
        json={"start_datetime": slots[1]["start_datetime"]},
    )
    assert response.status_code == 200
    assert captured == [created["id"]]


def test_reminder_worker_finds_upcoming_appointments(db_session: Session, monkeypatch) -> None:
    _create_upcoming_appointment(db_session, minutes_from_now=20)
    _create_upcoming_appointment(db_session, minutes_from_now=180)

    captured_calls: list[tuple[str, list[int] | None]] = []

    def fake_send_task(task_name: str, args=None, kwargs=None):
        captured_calls.append((task_name, args))
        return None

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(worker_tasks.celery_app, "send_task", fake_send_task)

    result = worker_tasks.schedule_upcoming_reminders(lookahead_minutes=60)
    assert result["checked"] == 1
    assert result["queued"] == 1
    assert len(captured_calls) == 1


def test_reminder_worker_enqueues_reminder_notification(db_session: Session, monkeypatch) -> None:
    appointment = _create_upcoming_appointment(db_session, minutes_from_now=15)
    queued: list[int] = []

    def fake_send_task(task_name: str, args=None, kwargs=None):
        if task_name == worker_tasks.REMINDER_TASK_NAME and args:
            queued.append(args[0])
        return None

    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(worker_tasks.celery_app, "send_task", fake_send_task)

    result = worker_tasks.schedule_upcoming_reminders(lookahead_minutes=60)
    assert result["queued"] == 1
    assert queued == [appointment.id]

    pending_notification = db_session.scalar(
        select(Notification).where(
            Notification.appointment_id == appointment.id,
            Notification.type == NotificationType.REMINDER,
            Notification.status == NotificationStatus.PENDING,
        )
    )
    assert pending_notification is not None


def test_notification_tasks_execute_successfully(db_session: Session, monkeypatch) -> None:
    appointment = _create_upcoming_appointment(db_session, minutes_from_now=25)
    monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: db_session)

    created_result = worker_tasks.notify_appointment_created(appointment.id)
    reminder_result = worker_tasks.notify_appointment_reminder(appointment.id)

    assert created_result["status"] == "sent"
    assert reminder_result["status"] == "sent"

    status_update = db_session.scalar(
        select(Notification).where(
            Notification.appointment_id == appointment.id,
            Notification.type == NotificationType.STATUS_UPDATE,
            Notification.status == NotificationStatus.SENT,
        )
    )
    reminder = db_session.scalar(
        select(Notification).where(
            Notification.appointment_id == appointment.id,
            Notification.type == NotificationType.REMINDER,
            Notification.status == NotificationStatus.SENT,
        )
    )
    assert status_update is not None
    assert status_update.payload_json is not None
    assert status_update.payload_json["event"] == "appointment_created"
    assert reminder is not None
    assert reminder.payload_json is not None
    assert reminder.payload_json["event"] == "appointment_reminder"
