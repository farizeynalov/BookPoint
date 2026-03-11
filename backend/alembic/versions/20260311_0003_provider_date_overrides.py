"""provider date overrides

Revision ID: 20260311_0003
Revises: 20260310_0002
Create Date: 2026-03-11 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0003"
down_revision: Union[str, None] = "20260310_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_date_overrides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("override_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(is_available = true AND start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time) "
            "OR (is_available = false AND start_time IS NULL AND end_time IS NULL)",
            name="ck_provider_date_overrides_time_shape",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_date_overrides_id", "provider_date_overrides", ["id"], unique=False)
    op.create_index(
        "ix_provider_date_overrides_provider_id",
        "provider_date_overrides",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_provider_date_overrides_override_date",
        "provider_date_overrides",
        ["override_date"],
        unique=False,
    )
    op.create_index(
        "ix_provider_date_overrides_provider_date",
        "provider_date_overrides",
        ["provider_id", "override_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_date_overrides_provider_date", table_name="provider_date_overrides")
    op.drop_index("ix_provider_date_overrides_override_date", table_name="provider_date_overrides")
    op.drop_index("ix_provider_date_overrides_provider_id", table_name="provider_date_overrides")
    op.drop_index("ix_provider_date_overrides_id", table_name="provider_date_overrides")
    op.drop_table("provider_date_overrides")
