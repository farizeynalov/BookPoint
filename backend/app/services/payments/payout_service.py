from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.enums import PayoutStatus, ProviderEarningStatus
from app.repositories.payout_repository import PayoutRepository
from app.repositories.provider_earning_repository import ProviderEarningRepository
from app.repositories.provider_repository import ProviderRepository
from app.services.notifications.dispatcher import (
    enqueue_payout_completed_notification,
    enqueue_payout_created_notification,
    enqueue_payout_failed_notification,
)
from app.services.payments.mock_provider import MockPayoutProvider


class PayoutService:
    def __init__(self, db: Session):
        self.db = db
        self.provider_repo = ProviderRepository(db)
        self.earning_repo = ProviderEarningRepository(db)
        self.payout_repo = PayoutRepository(db)
        self._providers = {
            "mock": MockPayoutProvider(),
        }

    def collect_provider_earnings(self, provider_id: int):
        return self.earning_repo.list_ready_for_payout(provider_id)

    def create_payout(self, provider_id: int):
        provider = self.provider_repo.get(provider_id)
        if provider is None:
            raise LookupError("Provider not found.")

        earnings = self.collect_provider_earnings(provider_id)
        if not earnings:
            raise ValueError("No earnings ready for payout.")

        currencies = {earning.currency for earning in earnings}
        if len(currencies) != 1:
            raise ValueError("Payout currency mismatch across earnings.")
        currency = currencies.pop()
        total_amount_minor = sum(int(earning.provider_amount_minor) for earning in earnings)
        if total_amount_minor <= 0:
            raise ValueError("No positive payout amount available.")

        try:
            payout = self.payout_repo.create(
                auto_commit=False,
                provider_id=provider.id,
                total_amount_minor=total_amount_minor,
                currency=currency,
                status=PayoutStatus.PENDING,
                provider_payout_reference=None,
                processed_at=None,
            )
            for earning in earnings:
                self.earning_repo.update(
                    earning,
                    auto_commit=False,
                    status=ProviderEarningStatus.PAID_OUT,
                    payout_id=payout.id,
                )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        enqueue_payout_created_notification(payout.id)
        return payout

    def mark_payout_completed(self, payout, *, provider_payout_reference: str | None = None):
        try:
            locked = self.payout_repo.get_for_update(payout.id)
            if locked is None:
                raise LookupError("Payout not found.")
            updated = self.payout_repo.update(
                locked,
                auto_commit=False,
                status=PayoutStatus.COMPLETED,
                provider_payout_reference=provider_payout_reference or locked.provider_payout_reference,
                processed_at=datetime.now(timezone.utc),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        enqueue_payout_completed_notification(updated.id)
        return updated

    def mark_payout_failed(self, payout, *, provider_payout_reference: str | None = None):
        try:
            locked = self.payout_repo.get_for_update(payout.id)
            if locked is None:
                raise LookupError("Payout not found.")
            linked_earnings = self.earning_repo.list_by_payout(locked.id)
            for earning in linked_earnings:
                self.earning_repo.update(
                    earning,
                    auto_commit=False,
                    status=ProviderEarningStatus.READY_FOR_PAYOUT,
                    payout_id=None,
                )
            updated = self.payout_repo.update(
                locked,
                auto_commit=False,
                status=PayoutStatus.FAILED,
                provider_payout_reference=provider_payout_reference or locked.provider_payout_reference,
                processed_at=datetime.now(timezone.utc),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        enqueue_payout_failed_notification(updated.id)
        return updated

    def _get_provider(self, provider_name: str):
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unsupported payout provider: {provider_name}")
        return provider

    def process_pending_payouts(self, *, provider_name: str = "mock") -> dict[str, int]:
        provider = self._get_provider(provider_name)
        pending_payouts = self.payout_repo.list_pending()
        processed = 0
        completed = 0
        failed = 0

        for pending in pending_payouts:
            processed += 1
            payout = self.payout_repo.get_for_update(pending.id)
            if payout is None:
                continue
            if payout.status != PayoutStatus.PENDING:
                continue
            try:
                self.payout_repo.update(
                    payout,
                    auto_commit=False,
                    status=PayoutStatus.PROCESSING,
                )
                self.db.commit()
                provider_result = provider.create_payout(
                    payout_id=payout.id,
                    provider_id=payout.provider_id,
                    amount_minor=payout.total_amount_minor,
                    currency=payout.currency,
                )
                if provider_result.get("status") == PayoutStatus.COMPLETED.value:
                    self.mark_payout_completed(
                        payout,
                        provider_payout_reference=provider_result.get("provider_payout_reference"),
                    )
                    completed += 1
                    continue
                self.mark_payout_failed(
                    payout,
                    provider_payout_reference=provider_result.get("provider_payout_reference"),
                )
                failed += 1
            except Exception:
                self.db.rollback()
                self.mark_payout_failed(payout)
                failed += 1

        return {
            "processed": processed,
            "completed": completed,
            "failed": failed,
        }
