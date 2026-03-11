import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260310_0002_provider_owned_services.py"
    )
    spec = importlib.util.spec_from_file_location("migration_20260310_0002_provider_owned_services", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_legacy_tables(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE providers (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE services (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                provider_id INTEGER NULL
            )
            """
        )
    )


def test_backfill_single_provider_org_succeeds() -> None:
    module = _load_migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _prepare_legacy_tables(conn)
        conn.execute(text("INSERT INTO providers (id, organization_id) VALUES (101, 1)"))
        conn.execute(text("INSERT INTO services (id, organization_id, provider_id) VALUES (1, 1, NULL)"))

        module._strict_backfill_legacy_service_provider_ids(conn)

        provider_id = conn.execute(
            text("SELECT provider_id FROM services WHERE id = 1")
        ).scalar_one()
        assert provider_id == 101


def test_backfill_zero_provider_org_fails() -> None:
    module = _load_migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _prepare_legacy_tables(conn)
        conn.execute(text("INSERT INTO services (id, organization_id, provider_id) VALUES (1, 1, NULL)"))

        with pytest.raises(RuntimeError) as exc_info:
            module._strict_backfill_legacy_service_provider_ids(conn)
        message = str(exc_info.value)
        assert "Cannot safely backfill services.provider_id" in message
        assert "zero-provider organization_ids=[1]" in message


def test_backfill_multi_provider_org_fails() -> None:
    module = _load_migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _prepare_legacy_tables(conn)
        conn.execute(text("INSERT INTO providers (id, organization_id) VALUES (201, 1), (202, 1)"))
        conn.execute(text("INSERT INTO services (id, organization_id, provider_id) VALUES (1, 1, NULL)"))

        with pytest.raises(RuntimeError) as exc_info:
            module._strict_backfill_legacy_service_provider_ids(conn)
        message = str(exc_info.value)
        assert "Cannot safely backfill services.provider_id" in message
        assert "multi-provider organization_ids=[1]" in message


def test_backfill_success_has_no_remaining_null_provider_ids() -> None:
    module = _load_migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _prepare_legacy_tables(conn)
        conn.execute(text("INSERT INTO providers (id, organization_id) VALUES (301, 1), (401, 2)"))
        conn.execute(
            text(
                """
                INSERT INTO services (id, organization_id, provider_id)
                VALUES
                    (1, 1, NULL),
                    (2, 1, NULL),
                    (3, 2, NULL),
                    (4, 2, 401)
                """
            )
        )

        module._strict_backfill_legacy_service_provider_ids(conn)

        remaining_null_count = conn.execute(
            text("SELECT COUNT(*) FROM services WHERE provider_id IS NULL")
        ).scalar_one()
        assert remaining_null_count == 0
