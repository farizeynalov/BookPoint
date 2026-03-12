from functools import lru_cache
import json
import logging
from typing import Any
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)
DEFAULT_SECRET_PLACEHOLDER = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BookPoint API"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    secret_key: str = DEFAULT_SECRET_PLACEHOLDER
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    payment_webhooks_enabled: bool = True
    payment_webhook_secret: str | None = None
    payment_pending_expiration_minutes: int = 15
    payment_expiration_check_interval_seconds: int = 60
    payout_processing_interval_seconds: int = 300
    enable_rate_limiting: bool = True
    rate_limit_use_redis: bool = False
    rate_limit_fallback_to_memory: bool = True
    rate_limit_public_slots_limit: int = 60
    rate_limit_public_slots_window_seconds: int = 60
    rate_limit_public_booking_limit: int = 12
    rate_limit_public_booking_window_seconds: int = 60
    rate_limit_public_booking_duplicate_limit: int = 1
    rate_limit_public_booking_duplicate_window_seconds: int = 20
    rate_limit_customer_booking_get_limit: int = 30
    rate_limit_customer_booking_get_window_seconds: int = 60
    rate_limit_customer_booking_action_limit: int = 12
    rate_limit_customer_booking_action_window_seconds: int = 60
    rate_limit_customer_invalid_token_limit: int = 10
    rate_limit_customer_invalid_token_window_seconds: int = 60
    rate_limit_payment_confirm_limit: int = 60
    rate_limit_payment_confirm_window_seconds: int = 60
    rate_limit_payout_create_limit: int = 20
    rate_limit_payout_create_window_seconds: int = 60
    rate_limit_manual_refund_limit: int = 20
    rate_limit_manual_refund_window_seconds: int = 60
    rate_limit_admin_events_limit: int = 30
    rate_limit_admin_events_window_seconds: int = 60

    database_url: str = "postgresql+psycopg://bookpoint:bookpoint@db:5432/bookpoint"
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    default_city: str = "Baku"
    default_timezone: str = "Asia/Baku"

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if raw == "":
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError("Invalid JSON array for cors_origins.") from exc
                if not isinstance(parsed, list):
                    raise ValueError("cors_origins JSON value must be an array.")
                return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        raise ValueError("Unsupported value for cors_origins.")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug"}:
                return True
            if normalized in {"0", "false", "no", "off", "", "release", "prod", "production"}:
                return False
        raise ValueError("Unsupported value for debug.")

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    def _validate_cors_structure(self) -> None:
        for origin in self.cors_origins:
            if origin == "*":
                if self.is_production:
                    raise ValueError("CORS wildcard origin is not allowed in production.")
                continue
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid CORS origin '{origin}'.")
            if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
                raise ValueError(f"CORS origin must not include path/query/fragment: '{origin}'.")

    def validate_runtime_safety(self) -> None:
        if self.is_production:
            if self.secret_key == DEFAULT_SECRET_PLACEHOLDER or not self.secret_key.strip():
                raise ValueError("SECRET_KEY must be set to a non-default value in production.")
            if self.debug:
                raise ValueError("DEBUG mode must be disabled in production.")
            if self.payment_webhooks_enabled and not (self.payment_webhook_secret and self.payment_webhook_secret.strip()):
                raise ValueError("PAYMENT_WEBHOOK_SECRET is required when payment webhooks are enabled in production.")
            if not self.enable_rate_limiting:
                logger.warning("Rate limiting is disabled in production mode.")
        elif self.secret_key == DEFAULT_SECRET_PLACEHOLDER:
            logger.warning("Using default SECRET_KEY outside production. Do not use this in deployed environments.")

        self._validate_cors_structure()
        self._validate_rate_limit_structure()

    def _validate_rate_limit_structure(self) -> None:
        integer_fields = (
            self.rate_limit_public_slots_limit,
            self.rate_limit_public_slots_window_seconds,
            self.rate_limit_public_booking_limit,
            self.rate_limit_public_booking_window_seconds,
            self.rate_limit_public_booking_duplicate_limit,
            self.rate_limit_public_booking_duplicate_window_seconds,
            self.rate_limit_customer_booking_get_limit,
            self.rate_limit_customer_booking_get_window_seconds,
            self.rate_limit_customer_booking_action_limit,
            self.rate_limit_customer_booking_action_window_seconds,
            self.rate_limit_customer_invalid_token_limit,
            self.rate_limit_customer_invalid_token_window_seconds,
            self.rate_limit_payment_confirm_limit,
            self.rate_limit_payment_confirm_window_seconds,
            self.rate_limit_payout_create_limit,
            self.rate_limit_payout_create_window_seconds,
            self.rate_limit_manual_refund_limit,
            self.rate_limit_manual_refund_window_seconds,
            self.rate_limit_admin_events_limit,
            self.rate_limit_admin_events_window_seconds,
        )
        if any(value <= 0 for value in integer_fields):
            raise ValueError("Rate limit limits and windows must be positive integers.")

    @model_validator(mode="after")
    def _run_runtime_validation(self):
        self.validate_runtime_safety()
        return self

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
