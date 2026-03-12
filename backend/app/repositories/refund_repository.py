from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import RefundStatus
from app.models.refund import Refund


class RefundRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> Refund:
        refund = Refund(**kwargs)
        self.db.add(refund)
        self.db.flush()
        self.db.refresh(refund)
        if auto_commit:
            self.db.commit()
        return refund

    def get(self, refund_id: int) -> Refund | None:
        return self.db.get(Refund, refund_id)

    def get_for_update(self, refund_id: int) -> Refund | None:
        stmt = select(Refund).where(Refund.id == refund_id).with_for_update()
        return self.db.scalar(stmt)

    def list_for_payment(self, payment_id: int) -> list[Refund]:
        stmt = (
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at.asc(), Refund.id.asc())
        )
        return list(self.db.scalars(stmt))

    def get_latest_for_payment(self, payment_id: int) -> Refund | None:
        stmt = (
            select(Refund)
            .where(Refund.payment_id == payment_id)
            .order_by(Refund.created_at.desc(), Refund.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def sum_succeeded_amount_for_payment(self, payment_id: int) -> int:
        stmt = (
            select(func.coalesce(func.sum(Refund.amount_minor), 0))
            .where(
                Refund.payment_id == payment_id,
                Refund.status == RefundStatus.SUCCEEDED,
            )
        )
        total = self.db.scalar(stmt)
        return int(total or 0)

    def update(self, refund: Refund, *, auto_commit: bool = True, **kwargs) -> Refund:
        for field, value in kwargs.items():
            setattr(refund, field, value)
        self.db.add(refund)
        self.db.flush()
        self.db.refresh(refund)
        if auto_commit:
            self.db.commit()
        return refund
