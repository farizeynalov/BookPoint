"""customer self-service booking access

Revision ID: 20260312_0007
Revises: 20260311_0006
Create Date: 2026-03-12 00:00:00.000000
"""

from __future__ import annotations

import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260312_0007"
down_revision: Union[str, None] = "20260311_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _generate_unique_reference(used: set[str]) -> str:
    while True:
        candidate = f"BKP-{secrets.token_hex(4).upper()}"
        if candidate not in used:
            used.add(candidate)
            return candidate


def _generate_unique_token(used: set[str]) -> str:
    while True:
        candidate = secrets.token_urlsafe(32)
        if candidate not in used:
            used.add(candidate)
            return candidate


def _backfill_access_fields(bind) -> None:
    rows = list(bind.execute(sa.text("SELECT id FROM appointments ORDER BY id ASC")).mappings())
    used_references: set[str] = set()
    used_tokens: set[str] = set()
    for row in rows:
        appointment_id = int(row["id"])
        bind.execute(
            sa.text(
                """
                UPDATE appointments
                SET booking_reference = :booking_reference,
                    booking_access_token = :booking_access_token
                WHERE id = :appointment_id
                """
            ),
            {
                "appointment_id": appointment_id,
                "booking_reference": _generate_unique_reference(used_references),
                "booking_access_token": _generate_unique_token(used_tokens),
            },
        )


def upgrade() -> None:
    op.add_column("appointments", sa.Column("booking_reference", sa.String(length=24), nullable=True))
    op.add_column("appointments", sa.Column("booking_access_token", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    _backfill_access_fields(bind)

    op.alter_column("appointments", "booking_reference", existing_type=sa.String(length=24), nullable=False)
    op.alter_column("appointments", "booking_access_token", existing_type=sa.String(length=128), nullable=False)
    op.create_index("ix_appointments_booking_reference", "appointments", ["booking_reference"], unique=True)
    op.create_index("ix_appointments_booking_access_token", "appointments", ["booking_access_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_appointments_booking_access_token", table_name="appointments")
    op.drop_index("ix_appointments_booking_reference", table_name="appointments")
    op.drop_column("appointments", "booking_access_token")
    op.drop_column("appointments", "booking_reference")
