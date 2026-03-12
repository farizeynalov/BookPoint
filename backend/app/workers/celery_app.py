import logging
from urllib.parse import urlparse

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "-"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}{parsed.path}"

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
            "schedule": float(settings.reminder_schedule_interval_seconds),
            "kwargs": {"lookahead_minutes": settings.reminder_lookahead_minutes},
        },
        "bookpoint-expire-pending-payments": {
            "task": "bookpoint.payments.expire_pending",
            "schedule": float(settings.payment_expiration_check_interval_seconds),
            "kwargs": {"expiration_minutes": settings.payment_pending_expiration_minutes},
        },
        "bookpoint-process-pending-payouts": {
            "task": "bookpoint.payouts.process_pending",
            "schedule": float(settings.payout_processing_interval_seconds),
            "kwargs": {"provider_name": settings.payout_processing_provider_name},
        },
        "bookpoint-cleanup-operational-data": {
            "task": "bookpoint.ops.cleanup_operational_data",
            "schedule": float(settings.ops_cleanup_interval_seconds),
            "kwargs": {
                "domain_events_retention_days": settings.domain_events_retention_days,
                "idempotency_keys_retention_days": settings.idempotency_keys_retention_days,
            },
        },
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

logger.info(
    "celery_config_loaded broker=%s backend=%s reminder_interval_seconds=%s payment_expiration_interval_seconds=%s "
    "payout_interval_seconds=%s ops_cleanup_interval_seconds=%s payout_provider=%s",
    _redact_url(settings.resolved_celery_broker_url),
    _redact_url(settings.resolved_celery_result_backend),
    settings.reminder_schedule_interval_seconds,
    settings.payment_expiration_check_interval_seconds,
    settings.payout_processing_interval_seconds,
    settings.ops_cleanup_interval_seconds,
    settings.payout_processing_provider_name,
)
