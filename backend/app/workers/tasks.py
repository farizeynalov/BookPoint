from app.workers.celery_app import celery_app


@celery_app.task(name="bookpoint.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="bookpoint.notifications.send_placeholder")
def send_notification_placeholder(notification_id: int) -> dict[str, str | int]:
    return {
        "notification_id": notification_id,
        "status": "placeholder_not_sent",
    }
