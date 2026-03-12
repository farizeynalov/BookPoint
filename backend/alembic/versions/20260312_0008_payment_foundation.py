"""payment foundation

Revision ID: 20260312_0008
Revises: 20260312_0007
Create Date: 2026-03-12 10:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260312_0008"
down_revision: Union[str, None] = "20260312_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


payment_status_enum = postgresql.ENUM(
    "pending",
    "requires_action",
    "succeeded",
    "failed",
    "canceled",
    "refunded",
    name="payment_status",
)
payment_type_enum = postgresql.ENUM("full", "deposit", name="payment_type")
payment_status_enum_ref = postgresql.ENUM(
    "pending",
    "requires_action",
    "succeeded",
    "failed",
    "canceled",
    "refunded",
    name="payment_status",
    create_type=False,
)
payment_type_enum_ref = postgresql.ENUM("full", "deposit", name="payment_type", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    payment_status_enum.create(bind, checkfirst=True)
    payment_type_enum.create(bind, checkfirst=True)

    op.add_column(
        "services",
        sa.Column("requires_payment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "services",
        sa.Column("payment_type", payment_type_enum_ref, nullable=False, server_default=sa.text("'full'")),
    )
    op.add_column("services", sa.Column("deposit_amount_minor", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_services_positive_deposit_amount_minor",
        "services",
        "deposit_amount_minor IS NULL OR deposit_amount_minor > 0",
    )
    op.create_check_constraint(
        "ck_services_deposit_requires_amount",
        "services",
        "(payment_type != 'deposit') OR deposit_amount_minor IS NOT NULL",
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("provider_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("provider_checkout_url", sa.String(length=1024), nullable=True),
        sa.Column("status", payment_status_enum_ref, nullable=False),
        sa.Column("payment_type", payment_type_enum_ref, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_payments_non_negative_amount_minor"),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_id", "payments", ["id"], unique=False)
    op.create_index("ix_payments_appointment_id", "payments", ["appointment_id"], unique=False)
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"], unique=False)
    op.create_index("ix_payments_status", "payments", ["status"], unique=False)
    op.create_index("ix_payments_provider_name", "payments", ["provider_name"], unique=False)
    op.create_index("ix_payments_provider_checkout_session_id", "payments", ["provider_checkout_session_id"], unique=True)
    op.create_index("ix_payments_provider_payment_intent_id", "payments", ["provider_payment_intent_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payments_provider_payment_intent_id", table_name="payments")
    op.drop_index("ix_payments_provider_checkout_session_id", table_name="payments")
    op.drop_index("ix_payments_provider_name", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_organization_id", table_name="payments")
    op.drop_index("ix_payments_appointment_id", table_name="payments")
    op.drop_index("ix_payments_id", table_name="payments")
    op.drop_table("payments")

    op.drop_constraint("ck_services_deposit_requires_amount", "services", type_="check")
    op.drop_constraint("ck_services_positive_deposit_amount_minor", "services", type_="check")
    op.drop_column("services", "deposit_amount_minor")
    op.drop_column("services", "payment_type")
    op.drop_column("services", "requires_payment")

    bind = op.get_bind()
    payment_status_enum.drop(bind, checkfirst=True)
    payment_type_enum.drop(bind, checkfirst=True)
