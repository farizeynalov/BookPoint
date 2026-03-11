"""provider owned services foundation

Revision ID: 20260310_0002
Revises: 20260308_0001
Create Date: 2026-03-10 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260310_0002"
down_revision: Union[str, None] = "20260308_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _strict_backfill_legacy_service_provider_ids(bind) -> None:
    org_ids_with_null_services = [
        int(row[0])
        for row in bind.execute(
            sa.text(
                """
                SELECT DISTINCT organization_id
                FROM services
                WHERE provider_id IS NULL
                ORDER BY organization_id
                """
            )
        )
    ]
    if not org_ids_with_null_services:
        return

    zero_provider_org_ids: list[int] = []
    multi_provider_org_ids: list[int] = []
    unambiguous_provider_map: dict[int, int] = {}

    for organization_id in org_ids_with_null_services:
        provider_stats = bind.execute(
            sa.text(
                """
                SELECT COUNT(*) AS provider_count, MIN(id) AS single_provider_id
                FROM providers
                WHERE organization_id = :organization_id
                """
            ),
            {"organization_id": organization_id},
        ).mappings().one()
        provider_count = int(provider_stats["provider_count"])
        if provider_count == 0:
            zero_provider_org_ids.append(organization_id)
            continue
        if provider_count > 1:
            multi_provider_org_ids.append(organization_id)
            continue
        unambiguous_provider_map[organization_id] = int(provider_stats["single_provider_id"])

    if zero_provider_org_ids or multi_provider_org_ids:
        details: list[str] = []
        if zero_provider_org_ids:
            details.append(f"zero-provider organization_ids={zero_provider_org_ids}")
        if multi_provider_org_ids:
            details.append(f"multi-provider organization_ids={multi_provider_org_ids}")
        raise RuntimeError(
            "Cannot safely backfill services.provider_id for legacy rows with NULL provider_id. "
            + "; ".join(details)
            + ". Manual data cleanup is required before rerunning this migration."
        )

    for organization_id, provider_id in unambiguous_provider_map.items():
        bind.execute(
            sa.text(
                """
                UPDATE services
                SET provider_id = :provider_id
                WHERE organization_id = :organization_id
                  AND provider_id IS NULL
                """
            ),
            {"provider_id": provider_id, "organization_id": organization_id},
        )

    remaining_null_provider_ids = bind.execute(
        sa.text("SELECT COUNT(*) FROM services WHERE provider_id IS NULL")
    ).scalar_one()
    if remaining_null_provider_ids:
        raise RuntimeError(
            "Cannot enforce provider-owned services: services.provider_id still contains NULL values after strict backfill."
        )


def upgrade() -> None:
    op.add_column("services", sa.Column("currency", sa.String(length=3), nullable=True))
    op.add_column(
        "services",
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "services",
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_services_non_negative_buffer_before",
        "services",
        "buffer_before_minutes >= 0",
    )
    op.create_check_constraint(
        "ck_services_non_negative_buffer_after",
        "services",
        "buffer_after_minutes >= 0",
    )

    bind = op.get_bind()
    _strict_backfill_legacy_service_provider_ids(bind)

    if bind.dialect.name == "postgresql":
        op.drop_constraint("services_provider_id_fkey", "services", type_="foreignkey")
        op.create_foreign_key(
            "fk_services_provider_id_providers",
            "services",
            "providers",
            ["provider_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.alter_column("services", "provider_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_services_provider_id_providers", "services", type_="foreignkey")
        op.create_foreign_key(
            "services_provider_id_fkey",
            "services",
            "providers",
            ["provider_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.alter_column("services", "provider_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint("ck_services_non_negative_buffer_after", "services", type_="check")
    op.drop_constraint("ck_services_non_negative_buffer_before", "services", type_="check")
    op.drop_column("services", "buffer_after_minutes")
    op.drop_column("services", "buffer_before_minutes")
    op.drop_column("services", "currency")
