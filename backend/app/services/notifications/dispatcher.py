import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TASK_APPOINTMENT_CREATED = "bookpoint.notifications.appointment_created"
TASK_APPOINTMENT_CANCELLED = "bookpoint.notifications.appointment_cancelled"
TASK_APPOINTMENT_RESCHEDULED = "bookpoint.notifications.appointment_rescheduled"


def _enqueue_notification_task(task_name: str, appointment_id: int) -> bool:
    try:
        celery_app.send_task(task_name, args=[appointment_id])
        logger.info("notification_task_enqueued task=%s appointment_id=%s", task_name, appointment_id)
        return True
    except Exception:
        logger.exception("notification_task_enqueue_failed task=%s appointment_id=%s", task_name, appointment_id)
        return False


def enqueue_appointment_created_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_CREATED, appointment_id)


def enqueue_appointment_cancelled_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_CANCELLED, appointment_id)


def enqueue_appointment_rescheduled_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_RESCHEDULED, appointment_id)
