from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_scope_and_key(self, *, scope: str, idempotency_key: str) -> IdempotencyKey | None:
        stmt = (
            select(IdempotencyKey)
            .where(
                IdempotencyKey.scope == scope,
                IdempotencyKey.idempotency_key == idempotency_key,
            )
            .limit(1)
        )
        return self.db.scalar(stmt)

    def create(self, *, auto_commit: bool = True, **kwargs) -> IdempotencyKey:
        record = IdempotencyKey(**kwargs)
        self.db.add(record)
        self.db.flush()
        self.db.refresh(record)
        if auto_commit:
            self.db.commit()
        return record

    def update(self, record: IdempotencyKey, *, auto_commit: bool = True, **kwargs) -> IdempotencyKey:
        for field, value in kwargs.items():
            setattr(record, field, value)
        self.db.add(record)
        self.db.flush()
        self.db.refresh(record)
        if auto_commit:
            self.db.commit()
        return record

    def delete(self, record: IdempotencyKey, *, auto_commit: bool = True) -> None:
        self.db.delete(record)
        self.db.flush()
        if auto_commit:
            self.db.commit()
