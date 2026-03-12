import pytest

from app.core.config import Settings


def test_cors_origins_parses_json_array(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000","http://127.0.0.1:3000"]')
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_cors_origins_parses_comma_separated(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_cors_origins_empty_or_missing_becomes_empty_list(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "")
    settings_empty = Settings(_env_file=None)
    assert settings_empty.cors_origins == []

    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings_missing = Settings(_env_file=None)
    assert settings_missing.cors_origins == []


def test_production_requires_non_default_secret_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "change-me-in-production")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "webhook-secret")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None)


def test_production_requires_payment_webhook_secret_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key")
    monkeypatch.setenv("PAYMENT_WEBHOOKS_ENABLED", "true")
    monkeypatch.delenv("PAYMENT_WEBHOOK_SECRET", raising=False)
    with pytest.raises(ValueError, match="PAYMENT_WEBHOOK_SECRET"):
        Settings(_env_file=None)


def test_production_rejects_wildcard_cors(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key")
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "prod-webhook-secret")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValueError, match="CORS wildcard"):
        Settings(_env_file=None)
