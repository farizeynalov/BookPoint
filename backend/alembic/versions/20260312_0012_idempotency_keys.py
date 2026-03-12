"""idempotency keys table

Revision ID: 20260312_0012
Revises: 20260312_0011
Create Date: 2026-03-12 22:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260312_0012"
down_revision: Union[str, None] = "20260312_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body_json", sa.JSON(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", "scope", name="uq_idempotency_keys_scope_key"),
    )
    op.create_index("ix_idempotency_keys_id", "idempotency_keys", ["id"], unique=False)
    op.create_index("ix_idempotency_keys_key", "idempotency_keys", ["idempotency_key"], unique=False)
    op.create_index("ix_idempotency_keys_scope", "idempotency_keys", ["scope"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_scope", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_key", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_keys_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
