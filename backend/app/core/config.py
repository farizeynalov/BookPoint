from functools import lru_cache
import json
from typing import Any
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "BookPoint API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

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
