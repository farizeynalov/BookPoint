import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260311_0006_multi_location_support.py"
    )
    spec = importlib.util.spec_from_file_location("migration_20260311_0006_multi_location_support", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_tables(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                city TEXT,
                address TEXT,
                timezone TEXT
            )
            """
        )
    )
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
                organization_id INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE appointments (
                id INTEGER PRIMARY KEY,
                provider_id INTEGER NOT NULL,
                location_id INTEGER NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE organization_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                address_line_1 TEXT NULL,
                city TEXT NULL,
                timezone TEXT NULL,
                is_active BOOLEAN NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE provider_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id INTEGER NOT NULL,
                location_id INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE service_locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id INTEGER NOT NULL,
                location_id INTEGER NOT NULL
            )
            """
        )
    )


def test_multi_location_backfill_populates_default_locations_and_assignments() -> None:
    module = _load_migration_module()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        _prepare_tables(conn)
        conn.execute(
            text(
                """
                INSERT INTO organizations (id, city, address, timezone)
                VALUES (1, 'Baku', 'A1', 'Asia/Baku'), (2, 'Baku', 'A2', 'Asia/Baku')
                """
            )
        )
        conn.execute(text("INSERT INTO providers (id, organization_id) VALUES (11, 1), (22, 2)"))
        conn.execute(text("INSERT INTO services (id, organization_id) VALUES (101, 1), (202, 2)"))
        conn.execute(text("INSERT INTO appointments (id, provider_id, location_id) VALUES (1001, 11, NULL), (1002, 22, NULL)"))

        module._create_default_locations(conn)
        mapping = module._default_location_map(conn)
        module._backfill_provider_locations(conn, mapping)
        module._backfill_service_locations(conn, mapping)
        module._backfill_appointments_location(conn, mapping)

        location_count = conn.execute(text("SELECT COUNT(*) FROM organization_locations")).scalar_one()
        provider_location_count = conn.execute(text("SELECT COUNT(*) FROM provider_locations")).scalar_one()
        service_location_count = conn.execute(text("SELECT COUNT(*) FROM service_locations")).scalar_one()
        appointment_null_count = conn.execute(text("SELECT COUNT(*) FROM appointments WHERE location_id IS NULL")).scalar_one()

        assert location_count == 2
        assert provider_location_count == 2
        assert service_location_count == 2
        assert appointment_null_count == 0
