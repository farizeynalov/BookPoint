from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import PayoutStatus
from app.models.payout import Payout


class PayoutRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> Payout:
        payout = Payout(**kwargs)
        self.db.add(payout)
        self.db.flush()
        self.db.refresh(payout)
        if auto_commit:
            self.db.commit()
        return payout

    def get(self, payout_id: int) -> Payout | None:
        return self.db.get(Payout, payout_id)

    def get_for_update(self, payout_id: int) -> Payout | None:
        stmt = select(Payout).where(Payout.id == payout_id).with_for_update()
        return self.db.scalar(stmt)

    def list_by_provider(self, provider_id: int) -> list[Payout]:
        stmt = (
            select(Payout)
            .where(Payout.provider_id == provider_id)
            .order_by(Payout.created_at.desc(), Payout.id.desc())
        )
        return list(self.db.scalars(stmt))

    def list_pending(self) -> list[Payout]:
        stmt = (
            select(Payout)
            .where(Payout.status == PayoutStatus.PENDING)
            .order_by(Payout.created_at.asc(), Payout.id.asc())
        )
        return list(self.db.scalars(stmt))

    def update(self, payout: Payout, *, auto_commit: bool = True, **kwargs) -> Payout:
        for field, value in kwargs.items():
            setattr(payout, field, value)
        self.db.add(payout)
        self.db.flush()
        self.db.refresh(payout)
        if auto_commit:
            self.db.commit()
        return payout
