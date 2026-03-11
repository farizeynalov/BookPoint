from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import NotificationStatus, NotificationType
from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> Notification:
        notification = Notification(**kwargs)
        self.db.add(notification)
        self.db.flush()
        self.db.refresh(notification)
        if auto_commit:
            self.db.commit()
        return notification

    def get(self, notification_id: int) -> Notification | None:
        return self.db.get(Notification, notification_id)

    def update(self, notification: Notification, *, auto_commit: bool = True, **kwargs) -> Notification:
        for field, value in kwargs.items():
            setattr(notification, field, value)
        self.db.add(notification)
        self.db.flush()
        self.db.refresh(notification)
        if auto_commit:
            self.db.commit()
        return notification

    def exists_for_appointment(
        self,
        *,
        appointment_id: int,
        notification_type: NotificationType,
        statuses: Sequence[NotificationStatus],
    ) -> bool:
        stmt = select(Notification.id).where(
            Notification.appointment_id == appointment_id,
            Notification.type == notification_type,
            Notification.status.in_(statuses),
        )
        return self.db.scalar(stmt) is not None

    def get_latest_pending_for_appointment(
        self,
        *,
        appointment_id: int,
        notification_type: NotificationType,
    ) -> Notification | None:
        stmt = (
            select(Notification)
            .where(
                Notification.appointment_id == appointment_id,
                Notification.type == notification_type,
                Notification.status == NotificationStatus.PENDING,
            )
            .order_by(Notification.id.desc())
        )
        return self.db.scalar(stmt)
