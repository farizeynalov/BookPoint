from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "bookpoint",
    broker=settings.resolved_celery_broker_url,
    backend=settings.resolved_celery_result_backend,
)

celery_app.conf.update(
    task_default_queue="bookpoint-default",
    imports=("app.workers.tasks",),
    beat_schedule={
        "bookpoint-schedule-upcoming-reminders": {
            "task": "bookpoint.notifications.schedule_upcoming_reminders",
            "schedule": 300.0,
            "kwargs": {"lookahead_minutes": 60},
        },
        "bookpoint-expire-pending-payments": {
            "task": "bookpoint.payments.expire_pending",
            "schedule": float(settings.payment_expiration_check_interval_seconds),
            "kwargs": {"expiration_minutes": settings.payment_pending_expiration_minutes},
        },
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
