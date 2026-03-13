"""whatsapp conversation state and message dedup

Revision ID: 20260313_0014
Revises: 20260312_0013
Create Date: 2026-03-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260313_0014"
down_revision: Union[str, None] = "20260312_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("conversation_states") as batch_op:
        batch_op.add_column(sa.Column("external_user_id", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("selected_organization_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("selected_provider_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("selected_service_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("selected_location_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("selected_slot_start", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_interaction_at", sa.DateTime(timezone=True), nullable=True))

        batch_op.create_foreign_key(
            "fk_conversation_states_selected_organization",
            "organizations",
            ["selected_organization_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_conversation_states_selected_provider",
            "providers",
            ["selected_provider_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_conversation_states_selected_service",
            "services",
            ["selected_service_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_conversation_states_selected_location",
            "organization_locations",
            ["selected_location_id"],
            ["id"],
            ondelete="SET NULL",
        )

    dialect_name = op.get_bind().dialect.name
    now_expression = "CURRENT_TIMESTAMP"
    if dialect_name == "postgresql":
        now_expression = "timezone('utc', now())"
    op.execute(
        f"""
        UPDATE conversation_states
        SET last_interaction_at = COALESCE(updated_at, created_at, {now_expression})
        WHERE last_interaction_at IS NULL
        """
    )

    with op.batch_alter_table("conversation_states") as batch_op:
        batch_op.alter_column(
            "last_interaction_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )
        batch_op.create_index("ix_conversation_states_external_user_id", ["external_user_id"], unique=False)
        batch_op.create_index("ix_conversation_states_selected_organization_id", ["selected_organization_id"], unique=False)
        batch_op.create_index("ix_conversation_states_selected_provider_id", ["selected_provider_id"], unique=False)
        batch_op.create_index("ix_conversation_states_selected_service_id", ["selected_service_id"], unique=False)
        batch_op.create_index("ix_conversation_states_selected_location_id", ["selected_location_id"], unique=False)
        batch_op.create_index("ix_conversation_states_last_interaction_at", ["last_interaction_at"], unique=False)

    with op.batch_alter_table("message_logs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_message_logs_channel_direction_external",
            ["channel", "direction", "external_message_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("message_logs") as batch_op:
        batch_op.drop_constraint("uq_message_logs_channel_direction_external", type_="unique")

    with op.batch_alter_table("conversation_states") as batch_op:
        batch_op.drop_index("ix_conversation_states_last_interaction_at")
        batch_op.drop_index("ix_conversation_states_selected_location_id")
        batch_op.drop_index("ix_conversation_states_selected_service_id")
        batch_op.drop_index("ix_conversation_states_selected_provider_id")
        batch_op.drop_index("ix_conversation_states_selected_organization_id")
        batch_op.drop_index("ix_conversation_states_external_user_id")
        batch_op.drop_constraint("fk_conversation_states_selected_location", type_="foreignkey")
        batch_op.drop_constraint("fk_conversation_states_selected_service", type_="foreignkey")
        batch_op.drop_constraint("fk_conversation_states_selected_provider", type_="foreignkey")
        batch_op.drop_constraint("fk_conversation_states_selected_organization", type_="foreignkey")
        batch_op.drop_column("last_interaction_at")
        batch_op.drop_column("selected_slot_start")
        batch_op.drop_column("selected_location_id")
        batch_op.drop_column("selected_service_id")
        batch_op.drop_column("selected_provider_id")
        batch_op.drop_column("selected_organization_id")
        batch_op.drop_column("external_user_id")
