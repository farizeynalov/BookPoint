from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.payment import Payment


class PaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, auto_commit: bool = True, **kwargs) -> Payment:
        payment = Payment(**kwargs)
        self.db.add(payment)
        self.db.flush()
        self.db.refresh(payment)
        if auto_commit:
            self.db.commit()
        return payment

    def get(self, payment_id: int) -> Payment | None:
        return self.db.get(Payment, payment_id)

    def get_for_update(self, payment_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id).with_for_update()
        return self.db.scalar(stmt)

    def get_by_checkout_session_id(self, provider_checkout_session_id: str) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.provider_checkout_session_id == provider_checkout_session_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_by_payment_intent_id(self, provider_payment_intent_id: str) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.provider_payment_intent_id == provider_payment_intent_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def get_latest_for_appointment(self, appointment_id: int) -> Payment | None:
        stmt = (
            select(Payment)
            .where(Payment.appointment_id == appointment_id)
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def list_for_appointment(self, appointment_id: int) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.appointment_id == appointment_id)
            .order_by(Payment.created_at.asc(), Payment.id.asc())
        )
        return list(self.db.scalars(stmt))

    def update(self, payment: Payment, *, auto_commit: bool = True, **kwargs) -> Payment:
        for field, value in kwargs.items():
            setattr(payment, field, value)
        self.db.add(payment)
        self.db.flush()
        self.db.refresh(payment)
        if auto_commit:
            self.db.commit()
        return payment
