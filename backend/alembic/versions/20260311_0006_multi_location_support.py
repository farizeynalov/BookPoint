"""multi location support

Revision ID: 20260311_0006
Revises: 20260311_0005
Create Date: 2026-03-11 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0006"
down_revision: Union[str, None] = "20260311_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_default_locations(bind) -> None:
    organizations = list(
        bind.execute(
            sa.text(
                """
                SELECT id, city, address, timezone
                FROM organizations
                ORDER BY id ASC
                """
            )
        ).mappings()
    )

    for organization in organizations:
        bind.execute(
            sa.text(
                """
                INSERT INTO organization_locations (
                    organization_id,
                    name,
                    slug,
                    address_line_1,
                    city,
                    timezone,
                    is_active
                ) VALUES (
                    :organization_id,
                    :name,
                    :slug,
                    :address_line_1,
                    :city,
                    :timezone,
                    :is_active
                )
                """
            ),
            {
                "organization_id": int(organization["id"]),
                "name": "Main Location",
                "slug": "main-location",
                "address_line_1": organization["address"],
                "city": organization["city"],
                "timezone": organization["timezone"],
                "is_active": True,
            },
        )


def _default_location_map(bind) -> dict[int, int]:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id
            FROM organization_locations
            ORDER BY id ASC
            """
        )
    ).mappings()
    org_to_location: dict[int, int] = {}
    for row in rows:
        organization_id = int(row["organization_id"])
        if organization_id not in org_to_location:
            org_to_location[organization_id] = int(row["id"])
    return org_to_location


def _backfill_appointments_location(bind, org_to_location: dict[int, int]) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT a.id AS appointment_id, p.organization_id
            FROM appointments a
            JOIN providers p ON p.id = a.provider_id
            ORDER BY a.id ASC
            """
        )
    ).mappings()

    for row in rows:
        organization_id = int(row["organization_id"])
        location_id = org_to_location.get(organization_id)
        if location_id is None:
            continue
        bind.execute(
            sa.text("UPDATE appointments SET location_id = :location_id WHERE id = :appointment_id"),
            {"location_id": location_id, "appointment_id": int(row["appointment_id"])},
        )


def _backfill_provider_locations(bind, org_to_location: dict[int, int]) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id
            FROM providers
            ORDER BY id ASC
            """
        )
    ).mappings()

    for row in rows:
        provider_id = int(row["id"])
        organization_id = int(row["organization_id"])
        location_id = org_to_location.get(organization_id)
        if location_id is None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO provider_locations (provider_id, location_id)
                VALUES (:provider_id, :location_id)
                """
            ),
            {"provider_id": provider_id, "location_id": location_id},
        )


def _backfill_service_locations(bind, org_to_location: dict[int, int]) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id
            FROM services
            ORDER BY id ASC
            """
        )
    ).mappings()

    for row in rows:
        service_id = int(row["id"])
        organization_id = int(row["organization_id"])
        location_id = org_to_location.get(organization_id)
        if location_id is None:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO service_locations (service_id, location_id)
                VALUES (:service_id, :location_id)
                """
            ),
            {"service_id": service_id, "location_id": location_id},
        )


def upgrade() -> None:
    op.create_table(
        "organization_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("address_line_1", sa.String(length=255), nullable=True),
        sa.Column("address_line_2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "slug", name="uq_organization_locations_org_slug"),
    )
    op.create_index("ix_organization_locations_id", "organization_locations", ["id"], unique=False)
    op.create_index("ix_organization_locations_organization_id", "organization_locations", ["organization_id"], unique=False)
    op.create_index("ix_organization_locations_slug", "organization_locations", ["slug"], unique=False)

    op.create_table(
        "provider_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["organization_locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "location_id", name="uq_provider_locations_provider_location"),
    )
    op.create_index("ix_provider_locations_id", "provider_locations", ["id"], unique=False)
    op.create_index("ix_provider_locations_provider_id", "provider_locations", ["provider_id"], unique=False)
    op.create_index("ix_provider_locations_location_id", "provider_locations", ["location_id"], unique=False)

    op.create_table(
        "service_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["organization_locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_id", "location_id", name="uq_service_locations_service_location"),
    )
    op.create_index("ix_service_locations_id", "service_locations", ["id"], unique=False)
    op.create_index("ix_service_locations_service_id", "service_locations", ["service_id"], unique=False)
    op.create_index("ix_service_locations_location_id", "service_locations", ["location_id"], unique=False)

    op.add_column("appointments", sa.Column("location_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    _create_default_locations(bind)
    org_to_location = _default_location_map(bind)
    _backfill_provider_locations(bind, org_to_location)
    _backfill_service_locations(bind, org_to_location)
    _backfill_appointments_location(bind, org_to_location)

    op.create_foreign_key(
        "fk_appointments_location_id_organization_locations",
        "appointments",
        "organization_locations",
        ["location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_appointments_location_id", "appointments", ["location_id"], unique=False)
    op.alter_column("appointments", "location_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_appointments_location_id", table_name="appointments")
    op.drop_constraint("fk_appointments_location_id_organization_locations", "appointments", type_="foreignkey")
    op.drop_column("appointments", "location_id")

    op.drop_index("ix_service_locations_location_id", table_name="service_locations")
    op.drop_index("ix_service_locations_service_id", table_name="service_locations")
    op.drop_index("ix_service_locations_id", table_name="service_locations")
    op.drop_table("service_locations")

    op.drop_index("ix_provider_locations_location_id", table_name="provider_locations")
    op.drop_index("ix_provider_locations_provider_id", table_name="provider_locations")
    op.drop_index("ix_provider_locations_id", table_name="provider_locations")
    op.drop_table("provider_locations")

    op.drop_index("ix_organization_locations_slug", table_name="organization_locations")
    op.drop_index("ix_organization_locations_organization_id", table_name="organization_locations")
    op.drop_index("ix_organization_locations_id", table_name="organization_locations")
    op.drop_table("organization_locations")
