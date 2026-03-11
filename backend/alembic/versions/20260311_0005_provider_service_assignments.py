"""provider service assignments

Revision ID: 20260311_0005
Revises: 20260311_0004
Create Date: 2026-03-11 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0005"
down_revision: Union[str, None] = "20260311_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("duration_minutes_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "duration_minutes_override IS NULL OR duration_minutes_override > 0",
            name="ck_provider_services_positive_duration_override",
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "service_id", name="uq_provider_services_provider_service"),
    )
    op.create_index("ix_provider_services_id", "provider_services", ["id"], unique=False)
    op.create_index("ix_provider_services_provider_id", "provider_services", ["provider_id"], unique=False)
    op.create_index("ix_provider_services_service_id", "provider_services", ["service_id"], unique=False)

    op.execute(
        """
        INSERT INTO provider_services (provider_id, service_id)
        SELECT s.provider_id, s.id
        FROM services s
        WHERE s.provider_id IS NOT NULL
        ON CONFLICT (provider_id, service_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_provider_services_service_id", table_name="provider_services")
    op.drop_index("ix_provider_services_provider_id", table_name="provider_services")
    op.drop_index("ix_provider_services_id", table_name="provider_services")
    op.drop_table("provider_services")
