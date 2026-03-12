import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TASK_APPOINTMENT_CREATED = "bookpoint.notifications.appointment_created"
TASK_APPOINTMENT_CANCELLED = "bookpoint.notifications.appointment_cancelled"
TASK_APPOINTMENT_RESCHEDULED = "bookpoint.notifications.appointment_rescheduled"
TASK_PAYMENT_REQUIRED = "bookpoint.notifications.payment_required"
TASK_PAYMENT_SUCCEEDED = "bookpoint.notifications.payment_succeeded"
TASK_PAYMENT_FAILED = "bookpoint.notifications.payment_failed"
TASK_BOOKING_AUTO_CANCELED_PAYMENT_TIMEOUT = "bookpoint.notifications.booking_auto_canceled_payment_timeout"
TASK_REFUND_INITIATED = "bookpoint.notifications.refund_initiated"
TASK_REFUND_SUCCEEDED = "bookpoint.notifications.refund_succeeded"
TASK_REFUND_FAILED = "bookpoint.notifications.refund_failed"
TASK_EARNING_CREATED = "bookpoint.notifications.earning_created"
TASK_PAYOUT_CREATED = "bookpoint.notifications.payout_created"
TASK_PAYOUT_COMPLETED = "bookpoint.notifications.payout_completed"
TASK_PAYOUT_FAILED = "bookpoint.notifications.payout_failed"


def _enqueue_notification_task(task_name: str, appointment_id: int) -> bool:
    try:
        celery_app.send_task(task_name, args=[appointment_id])
        logger.info("notification_task_enqueued task=%s appointment_id=%s", task_name, appointment_id)
        return True
    except Exception:
        logger.exception("notification_task_enqueue_failed task=%s appointment_id=%s", task_name, appointment_id)
        return False


def _enqueue_entity_task(task_name: str, *, entity_key: str, entity_id: int) -> bool:
    try:
        celery_app.send_task(task_name, args=[entity_id])
        logger.info("notification_task_enqueued task=%s %s=%s", task_name, entity_key, entity_id)
        return True
    except Exception:
        logger.exception("notification_task_enqueue_failed task=%s %s=%s", task_name, entity_key, entity_id)
        return False


def enqueue_appointment_created_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_CREATED, appointment_id)


def enqueue_appointment_cancelled_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_CANCELLED, appointment_id)


def enqueue_appointment_rescheduled_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_APPOINTMENT_RESCHEDULED, appointment_id)


def enqueue_payment_succeeded_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_PAYMENT_SUCCEEDED, appointment_id)


def enqueue_payment_failed_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_PAYMENT_FAILED, appointment_id)


def enqueue_payment_required_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_PAYMENT_REQUIRED, appointment_id)


def enqueue_booking_auto_canceled_payment_timeout_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_BOOKING_AUTO_CANCELED_PAYMENT_TIMEOUT, appointment_id)


def enqueue_refund_initiated_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_REFUND_INITIATED, appointment_id)


def enqueue_refund_succeeded_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_REFUND_SUCCEEDED, appointment_id)


def enqueue_refund_failed_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_REFUND_FAILED, appointment_id)


def enqueue_earning_created_notification(appointment_id: int) -> bool:
    return _enqueue_notification_task(TASK_EARNING_CREATED, appointment_id)


def enqueue_payout_created_notification(payout_id: int) -> bool:
    return _enqueue_entity_task(TASK_PAYOUT_CREATED, entity_key="payout_id", entity_id=payout_id)


def enqueue_payout_completed_notification(payout_id: int) -> bool:
    return _enqueue_entity_task(TASK_PAYOUT_COMPLETED, entity_key="payout_id", entity_id=payout_id)


def enqueue_payout_failed_notification(payout_id: int) -> bool:
    return _enqueue_entity_task(TASK_PAYOUT_FAILED, entity_key="payout_id", entity_id=payout_id)
