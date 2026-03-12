import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import AppointmentStatus, NotificationStatus, NotificationType
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.notification_repository import NotificationRepository
from app.services.notifications.service import (
    send_booking_auto_canceled_payment_timeout,
    send_payment_failed,
    send_payment_required,
    send_payment_succeeded,
    send_refund_failed,
    send_refund_initiated,
    send_refund_succeeded,
    send_booking_cancellation,
    send_booking_confirmation,
    send_booking_reminder,
    send_booking_reschedule,
)
from app.services.payments.service import PaymentService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

REMINDER_TASK_NAME = "bookpoint.notifications.appointment_reminder"
REMINDER_LOOKAHEAD_MINUTES = 60
PAYMENT_EXPIRATION_TASK_NAME = "bookpoint.payments.expire_pending"


@celery_app.task(name="bookpoint.ping")
def ping() -> str:
    return "pong"


def _execute_status_update_task(*, appointment_id: int, event_type: str, sender) -> dict[str, str | int]:
    logger.info("notification_task_start event=%s appointment_id=%s", event_type, appointment_id)
    db = SessionLocal()
    try:
        appointment_repo = AppointmentRepository(db)
        notification_repo = NotificationRepository(db)
        appointment = appointment_repo.get(appointment_id)
        if appointment is None:
            logger.warning("notification_task_appointment_missing event=%s appointment_id=%s", event_type, appointment_id)
            return {
                "event": event_type,
                "appointment_id": appointment_id,
                "status": "appointment_not_found",
            }

        payload = sender(appointment)
        notification = notification_repo.create(
            auto_commit=False,
            appointment_id=appointment.id,
            type=NotificationType.STATUS_UPDATE,
            status=NotificationStatus.SENT,
            scheduled_for=appointment.start_datetime,
            sent_at=datetime.now(timezone.utc),
            payload_json=payload,
        )
        db.commit()
        logger.info(
            "notification_task_success event=%s appointment_id=%s notification_id=%s",
            event_type,
            appointment.id,
            notification.id,
        )
        return {
            "event": event_type,
            "appointment_id": appointment.id,
            "notification_id": notification.id,
            "status": "sent",
        }
    except Exception:
        db.rollback()
        logger.exception("notification_task_failed event=%s appointment_id=%s", event_type, appointment_id)
        raise
    finally:
        db.close()


@celery_app.task(name="bookpoint.notifications.send_placeholder")
def send_notification_placeholder(notification_id: int) -> dict[str, str | int]:
    return {
        "notification_id": notification_id,
        "status": "placeholder_not_sent",
    }


@celery_app.task(name="bookpoint.notifications.appointment_created")
def notify_appointment_created(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="appointment_created",
        sender=send_booking_confirmation,
    )


@celery_app.task(name="bookpoint.notifications.appointment_cancelled")
def notify_appointment_cancelled(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="appointment_cancelled",
        sender=send_booking_cancellation,
    )


@celery_app.task(name="bookpoint.notifications.appointment_rescheduled")
def notify_appointment_rescheduled(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="appointment_rescheduled",
        sender=send_booking_reschedule,
    )


@celery_app.task(name="bookpoint.notifications.payment_succeeded")
def notify_payment_succeeded(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="payment_succeeded",
        sender=send_payment_succeeded,
    )


@celery_app.task(name="bookpoint.notifications.payment_required")
def notify_payment_required(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="payment_required",
        sender=send_payment_required,
    )


@celery_app.task(name="bookpoint.notifications.payment_failed")
def notify_payment_failed(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="payment_failed",
        sender=send_payment_failed,
    )


@celery_app.task(name="bookpoint.notifications.booking_auto_canceled_payment_timeout")
def notify_booking_auto_canceled_payment_timeout(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="booking_auto_canceled_due_to_payment_timeout",
        sender=send_booking_auto_canceled_payment_timeout,
    )


@celery_app.task(name="bookpoint.notifications.refund_initiated")
def notify_refund_initiated(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="refund_initiated",
        sender=send_refund_initiated,
    )


@celery_app.task(name="bookpoint.notifications.refund_succeeded")
def notify_refund_succeeded(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="refund_succeeded",
        sender=send_refund_succeeded,
    )


@celery_app.task(name="bookpoint.notifications.refund_failed")
def notify_refund_failed(appointment_id: int) -> dict[str, str | int]:
    return _execute_status_update_task(
        appointment_id=appointment_id,
        event_type="refund_failed",
        sender=send_refund_failed,
    )


@celery_app.task(name=REMINDER_TASK_NAME)
def notify_appointment_reminder(appointment_id: int) -> dict[str, str | int]:
    event_type = "appointment_reminder"
    logger.info("notification_task_start event=%s appointment_id=%s", event_type, appointment_id)
    db = SessionLocal()
    try:
        appointment_repo = AppointmentRepository(db)
        notification_repo = NotificationRepository(db)
        appointment = appointment_repo.get(appointment_id)
        if appointment is None:
            logger.warning("notification_task_appointment_missing event=%s appointment_id=%s", event_type, appointment_id)
            return {
                "event": event_type,
                "appointment_id": appointment_id,
                "status": "appointment_not_found",
            }

        payload = send_booking_reminder(appointment)
        pending = notification_repo.get_latest_pending_for_appointment(
            appointment_id=appointment.id,
            notification_type=NotificationType.REMINDER,
        )
        if pending is None:
            notification = notification_repo.create(
                auto_commit=False,
                appointment_id=appointment.id,
                type=NotificationType.REMINDER,
                status=NotificationStatus.SENT,
                scheduled_for=appointment.start_datetime,
                sent_at=datetime.now(timezone.utc),
                payload_json=payload,
            )
        else:
            notification = notification_repo.update(
                pending,
                auto_commit=False,
                status=NotificationStatus.SENT,
                sent_at=datetime.now(timezone.utc),
                payload_json=payload,
            )
        db.commit()
        logger.info(
            "notification_task_success event=%s appointment_id=%s notification_id=%s",
            event_type,
            appointment.id,
            notification.id,
        )
        return {
            "event": event_type,
            "appointment_id": appointment.id,
            "notification_id": notification.id,
            "status": "sent",
        }
    except Exception:
        db.rollback()
        logger.exception("notification_task_failed event=%s appointment_id=%s", event_type, appointment_id)
        raise
    finally:
        db.close()


@celery_app.task(name=PAYMENT_EXPIRATION_TASK_NAME)
def expire_pending_payments(expiration_minutes: int | None = None) -> dict[str, int]:
    db = SessionLocal()
    try:
        minutes = expiration_minutes if expiration_minutes is not None else settings.payment_pending_expiration_minutes
        result = PaymentService(db).expire_pending_payments(expiration_minutes=minutes)
        logger.info("payment_expiration_complete %s", result)
        return result
    except Exception:
        db.rollback()
        logger.exception("payment_expiration_failed")
        raise
    finally:
        db.close()


@celery_app.task(name="bookpoint.notifications.schedule_upcoming_reminders")
def schedule_upcoming_reminders(lookahead_minutes: int = REMINDER_LOOKAHEAD_MINUTES) -> dict[str, int]:
    logger.info("reminder_scheduler_start lookahead_minutes=%s", lookahead_minutes)
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=lookahead_minutes)
    checked = 0
    queued = 0
    skipped = 0
    failed = 0
    db = SessionLocal()
    try:
        appointment_repo = AppointmentRepository(db)
        notification_repo = NotificationRepository(db)
        appointments = appointment_repo.list_starting_between(
            start_datetime=now,
            end_datetime=window_end,
            statuses=(AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED),
        )
        for appointment in appointments:
            checked += 1
            if notification_repo.exists_for_appointment(
                appointment_id=appointment.id,
                notification_type=NotificationType.REMINDER,
                statuses=(NotificationStatus.PENDING, NotificationStatus.SENT),
            ):
                skipped += 1
                continue

            payload = {
                "event": "appointment_reminder_queued",
                "appointment_id": appointment.id,
                "provider_id": appointment.provider_id,
                "customer_id": appointment.customer_id,
                "scheduled_start": appointment.start_datetime.isoformat(),
                "scheduled_end": appointment.end_datetime.isoformat(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            pending_notification = notification_repo.create(
                auto_commit=False,
                appointment_id=appointment.id,
                type=NotificationType.REMINDER,
                status=NotificationStatus.PENDING,
                scheduled_for=appointment.start_datetime,
                payload_json=payload,
            )
            db.commit()
            try:
                celery_app.send_task(REMINDER_TASK_NAME, args=[appointment.id])
                queued += 1
                logger.info("reminder_scheduler_queued appointment_id=%s", appointment.id)
            except Exception:
                notification_repo.update(
                    pending_notification,
                    auto_commit=False,
                    status=NotificationStatus.FAILED,
                    payload_json={
                        "event": "appointment_reminder_queue_failed",
                        "appointment_id": appointment.id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                db.commit()
                failed += 1
                logger.exception("reminder_scheduler_enqueue_failed appointment_id=%s", appointment.id)

        result = {
            "checked": checked,
            "queued": queued,
            "skipped": skipped,
            "failed": failed,
        }
        logger.info("reminder_scheduler_complete %s", result)
        return result
    except Exception:
        db.rollback()
        logger.exception("reminder_scheduler_failed")
        raise
    finally:
        db.close()
