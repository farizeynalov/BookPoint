"""initial schema

Revision ID: 20260308_0001
Revises:
Create Date: 2026-03-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260308_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("business_type", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_id", "organizations", ["id"], unique=False)
    op.create_index("ix_organizations_name", "organizations", ["name"], unique=False)

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=False),
        sa.Column("phone_number_normalized", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("preferred_language", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customers_id", "customers", ["id"], unique=False)
    op.create_index("ix_customers_phone_number", "customers", ["phone_number"], unique=False)
    op.create_index("ix_customers_phone_number_normalized", "customers", ["phone_number_normalized"], unique=True)
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)

    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("OWNER", "MANAGER", "STAFF", "ASSISTANT", name="membership_role"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_member_org_user"),
    )
    op.create_index("ix_organization_members_id", "organization_members", ["id"], unique=False)
    op.create_index("ix_organization_members_organization_id", "organization_members", ["organization_id"], unique=False)
    op.create_index("ix_organization_members_user_id", "organization_members", ["user_id"], unique=False)

    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("appointment_duration_minutes", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("appointment_duration_minutes > 0", name="ck_providers_positive_duration"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_providers_user_id"),
    )
    op.create_index("ix_providers_id", "providers", ["id"], unique=False)
    op.create_index("ix_providers_organization_id", "providers", ["organization_id"], unique=False)

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("duration_minutes > 0", name="ck_services_positive_duration"),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_services_non_negative_price"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_services_id", "services", ["id"], unique=False)
    op.create_index("ix_services_name", "services", ["name"], unique=False)
    op.create_index("ix_services_organization_id", "services", ["organization_id"], unique=False)
    op.create_index("ix_services_provider_id", "services", ["provider_id"], unique=False)

    op.create_table(
        "customer_channel_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("WHATSAPP", "TELEGRAM", "WEB", "MOBILE", name="channel_type"),
            nullable=False,
        ),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("external_chat_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "channel", name="uq_customer_identity_customer_channel"),
        sa.UniqueConstraint("channel", "external_user_id", name="uq_customer_identity_channel_external_user"),
    )
    op.create_index("ix_customer_channel_identities_id", "customer_channel_identities", ["id"], unique=False)
    op.create_index("ix_customer_channel_identities_customer_id", "customer_channel_identities", ["customer_id"], unique=False)

    op.create_table(
        "provider_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_provider_availability_weekday_range"),
        sa.CheckConstraint("start_time < end_time", name="ck_provider_availability_start_before_end"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_id",
            "weekday",
            "start_time",
            "end_time",
            name="uq_provider_availability_provider_weekday_window",
        ),
    )
    op.create_index("ix_provider_availability_id", "provider_availability", ["id"], unique=False)
    op.create_index("ix_provider_availability_provider_id", "provider_availability", ["provider_id"], unique=False)

    op.create_table(
        "provider_time_off",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("start_datetime < end_datetime", name="ck_provider_time_off_start_before_end"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provider_time_off_id", "provider_time_off", ["id"], unique=False)
    op.create_index("ix_provider_time_off_provider_id", "provider_time_off", ["provider_id"], unique=False)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "CONFIRMED",
                "CANCELLED",
                "COMPLETED",
                "NO_SHOW",
                name="appointment_status",
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "booking_channel",
            sa.Enum(
                "WHATSAPP",
                "TELEGRAM",
                "WEB",
                "MOBILE",
                "DASHBOARD",
                "ADMIN",
                name="booking_channel",
            ),
            server_default="WEB",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("start_datetime < end_datetime", name="ck_appointments_start_before_end"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_appointments_id", "appointments", ["id"], unique=False)
    op.create_index("ix_appointments_organization_id", "appointments", ["organization_id"], unique=False)
    op.create_index("ix_appointments_provider_id", "appointments", ["provider_id"], unique=False)
    op.create_index("ix_appointments_service_id", "appointments", ["service_id"], unique=False)
    op.create_index("ix_appointments_customer_id", "appointments", ["customer_id"], unique=False)
    op.create_index("ix_appointments_start_datetime", "appointments", ["start_datetime"], unique=False)
    op.create_index("ix_appointments_end_datetime", "appointments", ["end_datetime"], unique=False)
    op.create_index("ix_appointments_status", "appointments", ["status"], unique=False)
    op.create_index("ix_appointments_provider_time_window", "appointments", ["provider_id", "start_datetime", "end_datetime"], unique=False)
    op.create_index("ix_appointments_org_start", "appointments", ["organization_id", "start_datetime"], unique=False)
    op.create_index("ix_appointments_customer_start", "appointments", ["customer_id", "start_datetime"], unique=False)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
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

    op.create_table(
        "conversation_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("WHATSAPP", "TELEGRAM", "WEB", "MOBILE", name="conversation_channel_type"),
            nullable=False,
        ),
        sa.Column("current_flow", sa.String(length=100), nullable=True),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id", "channel", name="uq_conversation_state_customer_channel"),
    )
    op.create_index("ix_conversation_states_id", "conversation_states", ["id"], unique=False)
    op.create_index("ix_conversation_states_customer_id", "conversation_states", ["customer_id"], unique=False)

    op.create_table(
        "message_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("INBOUND", "OUTBOUND", name="message_direction"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum("WHATSAPP", "TELEGRAM", "WEB", "MOBILE", name="message_channel_type"),
            nullable=False,
        ),
        sa.Column("external_message_id", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_logs_id", "message_logs", ["id"], unique=False)
    op.create_index("ix_message_logs_customer_id", "message_logs", ["customer_id"], unique=False)
    op.create_index("ix_message_logs_organization_id", "message_logs", ["organization_id"], unique=False)
    op.create_index("ix_message_logs_provider_id", "message_logs", ["provider_id"], unique=False)
    op.create_index("ix_message_logs_external_message_id", "message_logs", ["external_message_id"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum("REMINDER", "STATUS_UPDATE", name="notification_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "FAILED", name="notification_status"),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["appointments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"], unique=False)
    op.create_index("ix_notifications_appointment_id", "notifications", ["appointment_id"], unique=False)
    op.create_index("ix_notifications_status", "notifications", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_appointment_id", table_name="notifications")
    op.drop_index("ix_notifications_id", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_message_logs_external_message_id", table_name="message_logs")
    op.drop_index("ix_message_logs_provider_id", table_name="message_logs")
    op.drop_index("ix_message_logs_organization_id", table_name="message_logs")
    op.drop_index("ix_message_logs_customer_id", table_name="message_logs")
    op.drop_index("ix_message_logs_id", table_name="message_logs")
    op.drop_table("message_logs")

    op.drop_index("ix_conversation_states_customer_id", table_name="conversation_states")
    op.drop_index("ix_conversation_states_id", table_name="conversation_states")
    op.drop_table("conversation_states")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE appointments DROP CONSTRAINT IF EXISTS ex_appointments_provider_no_overlap")

    op.drop_index("ix_appointments_customer_start", table_name="appointments")
    op.drop_index("ix_appointments_org_start", table_name="appointments")
    op.drop_index("ix_appointments_provider_time_window", table_name="appointments")
    op.drop_index("ix_appointments_status", table_name="appointments")
    op.drop_index("ix_appointments_end_datetime", table_name="appointments")
    op.drop_index("ix_appointments_start_datetime", table_name="appointments")
    op.drop_index("ix_appointments_customer_id", table_name="appointments")
    op.drop_index("ix_appointments_service_id", table_name="appointments")
    op.drop_index("ix_appointments_provider_id", table_name="appointments")
    op.drop_index("ix_appointments_organization_id", table_name="appointments")
    op.drop_index("ix_appointments_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("ix_provider_time_off_provider_id", table_name="provider_time_off")
    op.drop_index("ix_provider_time_off_id", table_name="provider_time_off")
    op.drop_table("provider_time_off")

    op.drop_index("ix_provider_availability_provider_id", table_name="provider_availability")
    op.drop_index("ix_provider_availability_id", table_name="provider_availability")
    op.drop_table("provider_availability")

    op.drop_index("ix_customer_channel_identities_customer_id", table_name="customer_channel_identities")
    op.drop_index("ix_customer_channel_identities_id", table_name="customer_channel_identities")
    op.drop_table("customer_channel_identities")

    op.drop_index("ix_services_provider_id", table_name="services")
    op.drop_index("ix_services_organization_id", table_name="services")
    op.drop_index("ix_services_name", table_name="services")
    op.drop_index("ix_services_id", table_name="services")
    op.drop_table("services")

    op.drop_index("ix_providers_organization_id", table_name="providers")
    op.drop_index("ix_providers_id", table_name="providers")
    op.drop_table("providers")

    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_index("ix_organization_members_organization_id", table_name="organization_members")
    op.drop_index("ix_organization_members_id", table_name="organization_members")
    op.drop_table("organization_members")

    op.drop_index("ix_customers_phone_number_normalized", table_name="customers")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_index("ix_customers_phone_number", table_name="customers")
    op.drop_index("ix_customers_id", table_name="customers")
    op.drop_table("customers")

    op.drop_index("ix_organizations_name", table_name="organizations")
    op.drop_index("ix_organizations_id", table_name="organizations")
    op.drop_table("organizations")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")

    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS notification_status")
        op.execute("DROP TYPE IF EXISTS notification_type")
        op.execute("DROP TYPE IF EXISTS message_channel_type")
        op.execute("DROP TYPE IF EXISTS message_direction")
        op.execute("DROP TYPE IF EXISTS conversation_channel_type")
        op.execute("DROP TYPE IF EXISTS appointment_status")
        op.execute("DROP TYPE IF EXISTS booking_channel")
        op.execute("DROP TYPE IF EXISTS channel_type")
        op.execute("DROP TYPE IF EXISTS membership_role")
