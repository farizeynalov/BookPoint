from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.errors import http_exception_handler, unhandled_exception_handler, validation_exception_handler
from app.core.health import build_readiness_payload
from app.core.logging import configure_logging
from app.middleware.request_id import RequestIDMiddleware
from app.services.observability.metrics import render_prometheus_metrics

configure_logging()


def create_app(app_settings: Settings | None = None) -> FastAPI:
    config = app_settings or settings
    docs_enabled = config.enable_docs
    app = FastAPI(
        title=config.app_name,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/health/live", tags=["health"])
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def health_ready() -> JSONResponse:
        ready, payload = build_readiness_payload()
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    if config.enable_metrics:

        @app.get("/metrics", tags=["system"])
        def metrics() -> PlainTextResponse:
            return PlainTextResponse(
                render_prometheus_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

    app.include_router(api_router, prefix=config.api_v1_prefix)
    return app


app = create_app()
