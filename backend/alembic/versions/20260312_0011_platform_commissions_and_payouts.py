"""platform commissions and payouts

Revision ID: 20260312_0011
Revises: 20260312_0010
Create Date: 2026-03-12 18:45:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260312_0011"
down_revision: Union[str, None] = "20260312_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


commission_type_enum = postgresql.ENUM(
    "percentage",
    "fixed",
    name="commission_type",
)
commission_type_enum_ref = postgresql.ENUM(
    "percentage",
    "fixed",
    name="commission_type",
    create_type=False,
)

provider_earning_status_enum = postgresql.ENUM(
    "pending",
    "ready_for_payout",
    "paid_out",
    name="provider_earning_status",
)
provider_earning_status_enum_ref = postgresql.ENUM(
    "pending",
    "ready_for_payout",
    "paid_out",
    name="provider_earning_status",
    create_type=False,
)

payout_status_enum = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="payout_status",
)
payout_status_enum_ref = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="payout_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        commission_type_enum.create(bind, checkfirst=True)
        provider_earning_status_enum.create(bind, checkfirst=True)
        payout_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "organizations",
        sa.Column(
            "commission_type",
            commission_type_enum_ref if bind.dialect.name == "postgresql" else sa.String(length=32),
            nullable=False,
            server_default=sa.text("'percentage'"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "commission_percentage",
            sa.Numeric(5, 4),
            nullable=False,
            server_default=sa.text("0.10"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("commission_fixed_minor", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_organizations_commission_percentage_range",
        "organizations",
        "commission_percentage >= 0 AND commission_percentage <= 1",
    )
    op.create_check_constraint(
        "ck_organizations_commission_fixed_non_negative",
        "organizations",
        "commission_fixed_minor >= 0",
    )

    op.create_table(
        "payouts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("total_amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            payout_status_enum_ref if bind.dialect.name == "postgresql" else sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("provider_payout_reference", sa.String(length=255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("total_amount_minor >= 0", name="ck_payouts_non_negative_total_amount_minor"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payouts_id", "payouts", ["id"], unique=False)
    op.create_index("ix_payouts_provider_id", "payouts", ["provider_id"], unique=False)
    op.create_index("ix_payouts_status", "payouts", ["status"], unique=False)
    op.create_index("ix_payouts_provider_payout_reference", "payouts", ["provider_payout_reference"], unique=False)

    op.create_table(
        "provider_earnings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("payout_id", sa.Integer(), nullable=True),
        sa.Column("gross_amount_minor", sa.Integer(), nullable=False),
        sa.Column("platform_fee_minor", sa.Integer(), nullable=False),
        sa.Column("provider_amount_minor", sa.Integer(), nullable=False),
        sa.Column("refunded_amount_minor", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("adjustment_pending_minor", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            provider_earning_status_enum_ref if bind.dialect.name == "postgresql" else sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("gross_amount_minor >= 0", name="ck_provider_earnings_non_negative_gross"),
        sa.CheckConstraint("platform_fee_minor >= 0", name="ck_provider_earnings_non_negative_platform_fee"),
        sa.CheckConstraint("provider_amount_minor >= 0", name="ck_provider_earnings_non_negative_provider_amount"),
        sa.CheckConstraint("refunded_amount_minor >= 0", name="ck_provider_earnings_non_negative_refunded_amount"),
        sa.CheckConstraint(
            "adjustment_pending_minor >= 0",
            name="ck_provider_earnings_non_negative_adjustment_pending",
        ),
        sa.CheckConstraint(
            "platform_fee_minor + provider_amount_minor <= gross_amount_minor",
            name="ck_provider_earnings_provider_plus_fee_lte_gross",
        ),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payout_id"], ["payouts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_provider_earnings_payment_id"),
    )
    op.create_index("ix_provider_earnings_id", "provider_earnings", ["id"], unique=False)
    op.create_index("ix_provider_earnings_provider_id", "provider_earnings", ["provider_id"], unique=False)
    op.create_index("ix_provider_earnings_appointment_id", "provider_earnings", ["appointment_id"], unique=False)
    op.create_index("ix_provider_earnings_payment_id", "provider_earnings", ["payment_id"], unique=False)
    op.create_index("ix_provider_earnings_payout_id", "provider_earnings", ["payout_id"], unique=False)
    op.create_index("ix_provider_earnings_status", "provider_earnings", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_provider_earnings_status", table_name="provider_earnings")
    op.drop_index("ix_provider_earnings_payout_id", table_name="provider_earnings")
    op.drop_index("ix_provider_earnings_payment_id", table_name="provider_earnings")
    op.drop_index("ix_provider_earnings_appointment_id", table_name="provider_earnings")
    op.drop_index("ix_provider_earnings_provider_id", table_name="provider_earnings")
    op.drop_index("ix_provider_earnings_id", table_name="provider_earnings")
    op.drop_table("provider_earnings")

    op.drop_index("ix_payouts_provider_payout_reference", table_name="payouts")
    op.drop_index("ix_payouts_status", table_name="payouts")
    op.drop_index("ix_payouts_provider_id", table_name="payouts")
    op.drop_index("ix_payouts_id", table_name="payouts")
    op.drop_table("payouts")

    op.drop_constraint("ck_organizations_commission_fixed_non_negative", "organizations", type_="check")
    op.drop_constraint("ck_organizations_commission_percentage_range", "organizations", type_="check")
    op.drop_column("organizations", "commission_fixed_minor")
    op.drop_column("organizations", "commission_percentage")
    op.drop_column("organizations", "commission_type")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        payout_status_enum.drop(bind, checkfirst=True)
        provider_earning_status_enum.drop(bind, checkfirst=True)
        commission_type_enum.drop(bind, checkfirst=True)
