from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey
from app.repositories.idempotency_repository import IdempotencyRepository
from app.services.observability.domain_events import record_domain_event
from app.services.observability.metrics import increment_counter

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
MAX_IDEMPOTENCY_KEY_LENGTH = 255


class IdempotencyValidationError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


@dataclass
class IdempotencyStartResult:
    record: IdempotencyKey | None = None
    replay_response: JSONResponse | None = None


class IdempotencyService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = IdempotencyRepository(db)

    @staticmethod
    def normalize_key(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise IdempotencyValidationError("Idempotency key is too long.")
        return normalized

    @staticmethod
    def _hash_payload(payload: Any) -> str:
        normalized_payload = jsonable_encoder(payload)
        serialized = json.dumps(normalized_payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _resolve_existing(self, *, existing: IdempotencyKey, request_hash: str) -> IdempotencyStartResult:
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency key was already used with a different request.")
        if existing.response_status_code is None or existing.response_body_json is None:
            raise IdempotencyConflictError("Idempotency key is already being processed.")
        increment_counter("idempotency_replays_total")
        record_domain_event(
            self.db,
            event_type="idempotency_replayed",
            entity_type=existing.resource_type or "idempotency_key",
            entity_id=existing.resource_id or existing.id,
            actor_type="system",
            status="info",
            payload={
                "scope": existing.scope,
                "idempotency_key": existing.idempotency_key,
                "resource_type": existing.resource_type,
                "resource_id": existing.resource_id,
            },
        )
        logger.info(
            "idempotency_replay scope=%s key=%s record_id=%s",
            existing.scope,
            existing.idempotency_key,
            existing.id,
        )
        return IdempotencyStartResult(
            replay_response=JSONResponse(
                status_code=existing.response_status_code,
                content=existing.response_body_json,
                headers={"X-Idempotent-Replayed": "true"},
            )
        )

    def start_request(
        self,
        *,
        idempotency_key: str | None,
        scope: str,
        request_payload: Any,
    ) -> IdempotencyStartResult:
        normalized_key = self.normalize_key(idempotency_key)
        if normalized_key is None:
            return IdempotencyStartResult()

        request_hash = self._hash_payload(request_payload)
        existing = self.repo.get_by_scope_and_key(scope=scope, idempotency_key=normalized_key)
        if existing is not None:
            return self._resolve_existing(existing=existing, request_hash=request_hash)

        try:
            record = self.repo.create(
                auto_commit=True,
                idempotency_key=normalized_key,
                scope=scope,
                request_hash=request_hash,
                response_status_code=None,
                response_body_json=None,
                resource_type=None,
                resource_id=None,
            )
        except IntegrityError:
            self.db.rollback()
            raced = self.repo.get_by_scope_and_key(scope=scope, idempotency_key=normalized_key)
            if raced is None:
                raise
            return self._resolve_existing(existing=raced, request_hash=request_hash)

        logger.info("idempotency_record_created scope=%s key=%s record_id=%s", scope, normalized_key, record.id)
        return IdempotencyStartResult(record=record)

    def finalize_success(
        self,
        *,
        record: IdempotencyKey | None,
        status_code: int,
        response_body: Any,
        resource_type: str | None = None,
        resource_id: int | None = None,
    ) -> None:
        if record is None:
            return
        serialized = jsonable_encoder(response_body)
        self.repo.update(
            record,
            auto_commit=True,
            response_status_code=status_code,
            response_body_json=serialized,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        logger.info(
            "idempotency_record_finalized scope=%s key=%s record_id=%s status_code=%s",
            record.scope,
            record.idempotency_key,
            record.id,
            status_code,
        )

    def abort(self, *, record: IdempotencyKey | None) -> None:
        if record is None:
            return
        try:
            self.repo.delete(record, auto_commit=True)
            logger.info(
                "idempotency_record_aborted scope=%s key=%s record_id=%s",
                record.scope,
                record.idempotency_key,
                record.id,
            )
        except Exception:
            self.db.rollback()
            logger.exception(
                "idempotency_record_abort_failed scope=%s key=%s record_id=%s",
                record.scope,
                record.idempotency_key,
                record.id,
            )
