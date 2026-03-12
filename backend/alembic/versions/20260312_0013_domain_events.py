"""domain events table

Revision ID: 20260312_0013
Revises: 20260312_0012
Create Date: 2026-03-12 23:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260312_0013"
down_revision: Union[str, None] = "20260312_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default=sa.text("'system'")),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("related_payment_id", sa.Integer(), nullable=True),
        sa.Column("related_appointment_id", sa.Integer(), nullable=True),
        sa.Column("related_payout_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'info'")),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_payment_id"], ["payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_appointment_id"], ["appointments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_payout_id"], ["payouts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_domain_events_id", "domain_events", ["id"], unique=False)
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"], unique=False)
    op.create_index("ix_domain_events_organization_id", "domain_events", ["organization_id"], unique=False)
    op.create_index("ix_domain_events_entity_type", "domain_events", ["entity_type"], unique=False)
    op.create_index("ix_domain_events_entity_id", "domain_events", ["entity_id"], unique=False)
    op.create_index("ix_domain_events_entity_lookup", "domain_events", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_domain_events_status", "domain_events", ["status"], unique=False)
    op.create_index("ix_domain_events_created_at", "domain_events", ["created_at"], unique=False)
    op.create_index("ix_domain_events_request_id", "domain_events", ["request_id"], unique=False)
    op.create_index("ix_domain_events_related_payment_id", "domain_events", ["related_payment_id"], unique=False)
    op.create_index("ix_domain_events_related_appointment_id", "domain_events", ["related_appointment_id"], unique=False)
    op.create_index("ix_domain_events_related_payout_id", "domain_events", ["related_payout_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_domain_events_related_payout_id", table_name="domain_events")
    op.drop_index("ix_domain_events_related_appointment_id", table_name="domain_events")
    op.drop_index("ix_domain_events_related_payment_id", table_name="domain_events")
    op.drop_index("ix_domain_events_request_id", table_name="domain_events")
    op.drop_index("ix_domain_events_created_at", table_name="domain_events")
    op.drop_index("ix_domain_events_status", table_name="domain_events")
    op.drop_index("ix_domain_events_entity_lookup", table_name="domain_events")
    op.drop_index("ix_domain_events_entity_id", table_name="domain_events")
    op.drop_index("ix_domain_events_entity_type", table_name="domain_events")
    op.drop_index("ix_domain_events_organization_id", table_name="domain_events")
    op.drop_index("ix_domain_events_event_type", table_name="domain_events")
    op.drop_index("ix_domain_events_id", table_name="domain_events")
    op.drop_table("domain_events")
