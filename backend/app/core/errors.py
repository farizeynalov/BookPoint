from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id

logger = logging.getLogger(__name__)

_DEFAULT_ERROR_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "resource_not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_server_error",
}


def _resolve_request_id(request: Request) -> str:
    state_request_id = getattr(request.state, "request_id", None)
    if isinstance(state_request_id, str) and state_request_id:
        return state_request_id
    return get_request_id() or "unknown"


def _normalize_message(detail: Any, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    if isinstance(detail, Mapping):
        candidate = detail.get("message")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return fallback


def _normalize_code(status_code: int, detail: Any) -> str:
    if isinstance(detail, Mapping):
        detail_code = detail.get("code")
        if isinstance(detail_code, str) and detail_code.strip():
            return detail_code.strip()
    return _DEFAULT_ERROR_CODES.get(status_code, "request_failed")


def _normalize_details(detail: Any) -> dict[str, Any] | None:
    if not isinstance(detail, Mapping):
        return None
    if isinstance(detail.get("details"), Mapping):
        return dict(detail["details"])
    filtered = {k: v for k, v in detail.items() if k not in {"code", "message"}}
    if not filtered:
        return None
    return filtered


def build_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _resolve_request_id(request)
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
        "detail": message,
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        headers=dict(headers or {}),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return build_error_response(
        request=request,
        status_code=exc.status_code,
        code=_normalize_code(exc.status_code, exc.detail),
        message=_normalize_message(exc.detail, fallback="Request failed."),
        details=_normalize_details(exc.detail),
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return build_error_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message="Request validation failed.",
        details={"errors": exc.errors()},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_api_exception method=%s path=%s",
        request.method,
        request.url.path,
    )
    return build_error_response(
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_server_error",
        message="Internal server error.",
    )
