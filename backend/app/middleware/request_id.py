from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128


def _sanitize_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > MAX_REQUEST_ID_LENGTH:
        return None
    if any(ord(char) < 33 or ord(char) > 126 for char in normalized):
        return None
    return normalized


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_id = _sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = incoming_id or uuid.uuid4().hex
        request.state.request_id = request_id

        token = set_request_id(request_id)
        started_at = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            logger.info(
                "http_request_complete method=%s path=%s status_code=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                response.status_code if response is not None else 500,
                elapsed_ms,
            )
            reset_request_id(token)

        if response is None:
            raise RuntimeError("Response was not produced by downstream middleware.")
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
