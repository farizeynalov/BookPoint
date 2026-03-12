"""refunds and cancellation policies

Revision ID: 20260312_0010
Revises: 20260312_0009
Create Date: 2026-03-12 16:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260312_0010"
down_revision: Union[str, None] = "20260312_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


cancellation_policy_type_enum = postgresql.ENUM(
    "flexible",
    "moderate",
    "strict",
    name="cancellation_policy_type",
)
cancellation_policy_type_enum_ref = postgresql.ENUM(
    "flexible",
    "moderate",
    "strict",
    name="cancellation_policy_type",
    create_type=False,
)
refund_status_enum = postgresql.ENUM(
    "pending",
    "succeeded",
    "failed",
    name="refund_status",
)
refund_status_enum_ref = postgresql.ENUM(
    "pending",
    "succeeded",
    "failed",
    name="refund_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        cancellation_policy_type_enum.create(bind, checkfirst=True)
        refund_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "services",
        sa.Column(
            "cancellation_policy_type",
            cancellation_policy_type_enum_ref if bind.dialect.name == "postgresql" else sa.String(length=32),
            nullable=False,
            server_default=sa.text("'flexible'"),
        ),
    )
    op.add_column(
        "services",
        sa.Column("cancellation_window_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
    )
    op.create_check_constraint(
        "ck_services_non_negative_cancellation_window_hours",
        "services",
        "cancellation_window_hours >= 0",
    )

    op.create_table(
        "refunds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider_refund_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            refund_status_enum_ref if bind.dialect.name == "postgresql" else sa.String(length=32),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_refunds_non_negative_amount_minor"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refunds_id", "refunds", ["id"], unique=False)
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"], unique=False)
    op.create_index("ix_refunds_status", "refunds", ["status"], unique=False)
    op.create_index("ix_refunds_provider_refund_id", "refunds", ["provider_refund_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refunds_provider_refund_id", table_name="refunds")
    op.drop_index("ix_refunds_status", table_name="refunds")
    op.drop_index("ix_refunds_payment_id", table_name="refunds")
    op.drop_index("ix_refunds_id", table_name="refunds")
    op.drop_table("refunds")

    op.drop_constraint("ck_services_non_negative_cancellation_window_hours", "services", type_="check")
    op.drop_column("services", "cancellation_window_hours")
    op.drop_column("services", "cancellation_policy_type")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        refund_status_enum.drop(bind, checkfirst=True)
        cancellation_policy_type_enum.drop(bind, checkfirst=True)
