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
