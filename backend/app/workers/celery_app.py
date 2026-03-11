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
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
