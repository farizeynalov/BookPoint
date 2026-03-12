from __future__ import annotations

from contextvars import ContextVar, Token

REQUEST_ID_CTX_VAR: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str | None) -> Token[str | None]:
    return REQUEST_ID_CTX_VAR.set(request_id)


def get_request_id() -> str | None:
    return REQUEST_ID_CTX_VAR.get()


def reset_request_id(token: Token[str | None]) -> None:
    REQUEST_ID_CTX_VAR.reset(token)
