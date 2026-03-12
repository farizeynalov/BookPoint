"""pending payment enforcement

Revision ID: 20260312_0009
Revises: 20260312_0008
Create Date: 2026-03-12 14:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260312_0009"
down_revision: Union[str, None] = "20260312_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'PENDING_PAYMENT'")
    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_provider_no_overlap")
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_provider_no_overlap
        EXCLUDE USING gist (
            provider_id WITH =,
            tstzrange(start_datetime, end_datetime, '[)') WITH &&
        )
        WHERE (status IN ('PENDING', 'PENDING_PAYMENT', 'CONFIRMED'));
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_provider_no_overlap")
    op.execute(
        """
        ALTER TABLE appointments
        ADD CONSTRAINT ex_appointments_provider_no_overlap
        EXCLUDE USING gist (
            provider_id WITH =,
            tstzrange(start_datetime, end_datetime, '[)') WITH &&
        )
        WHERE (status IN ('PENDING', 'CONFIRMED'));
        """
    )
