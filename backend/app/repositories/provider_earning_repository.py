from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ProviderEarningStatus
from app.models.provider_earning import ProviderEarning


class ProviderEarningRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> ProviderEarning:
        earning = ProviderEarning(**kwargs)
        self.db.add(earning)
        self.db.flush()
        self.db.refresh(earning)
        if auto_commit:
            self.db.commit()
        return earning

    def get(self, earning_id: int) -> ProviderEarning | None:
        return self.db.get(ProviderEarning, earning_id)

    def get_for_update(self, earning_id: int) -> ProviderEarning | None:
        stmt = select(ProviderEarning).where(ProviderEarning.id == earning_id).with_for_update()
        return self.db.scalar(stmt)

    def get_by_payment_id(self, payment_id: int) -> ProviderEarning | None:
        stmt = select(ProviderEarning).where(ProviderEarning.payment_id == payment_id).limit(1)
        return self.db.scalar(stmt)

    def get_by_payment_id_for_update(self, payment_id: int) -> ProviderEarning | None:
        stmt = (
            select(ProviderEarning)
            .where(ProviderEarning.payment_id == payment_id)
            .with_for_update()
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_by_provider(self, provider_id: int) -> list[ProviderEarning]:
        stmt = (
            select(ProviderEarning)
            .where(ProviderEarning.provider_id == provider_id)
            .order_by(ProviderEarning.created_at.desc(), ProviderEarning.id.desc())
        )
        return list(self.db.scalars(stmt))

    def list_ready_for_payout(self, provider_id: int) -> list[ProviderEarning]:
        stmt = (
            select(ProviderEarning)
            .where(
                ProviderEarning.provider_id == provider_id,
                ProviderEarning.status == ProviderEarningStatus.READY_FOR_PAYOUT,
                ProviderEarning.provider_amount_minor > 0,
                ProviderEarning.payout_id.is_(None),
            )
            .order_by(ProviderEarning.id.asc())
        )
        return list(self.db.scalars(stmt))

    def list_by_payout(self, payout_id: int) -> list[ProviderEarning]:
        stmt = (
            select(ProviderEarning)
            .where(ProviderEarning.payout_id == payout_id)
            .order_by(ProviderEarning.id.asc())
        )
        return list(self.db.scalars(stmt))

    def update(self, earning: ProviderEarning, *, auto_commit: bool = True, **kwargs) -> ProviderEarning:
        for field, value in kwargs.items():
            setattr(earning, field, value)
        self.db.add(earning)
        self.db.flush()
        self.db.refresh(earning)
        if auto_commit:
            self.db.commit()
        return earning
