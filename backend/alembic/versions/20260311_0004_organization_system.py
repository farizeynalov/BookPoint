"""organization system slug + memberships alignment

Revision ID: 20260311_0004
Revises: 20260311_0003
Create Date: 2026-03-11 12:00:00.000000
"""

from __future__ import annotations

import re
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260311_0004"
down_revision: Union[str, None] = "20260311_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MULTI_DASH_PATTERN = re.compile(r"-+")
_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower().strip()
    slug = _NON_ALNUM_PATTERN.sub("-", lowered).strip("-")
    slug = _MULTI_DASH_PATTERN.sub("-", slug)
    return slug or "organization"


def _rename_membership_table_if_needed(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "organization_members" in tables and "organization_memberships" not in tables:
        op.rename_table("organization_members", "organization_memberships")


def _backfill_organization_slugs(bind) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT id, name
            FROM organizations
            ORDER BY id ASC
            """
        )
    ).mappings()

    used_slugs: set[str] = set()
    for row in rows:
        org_id = int(row["id"])
        name = str(row["name"] or "").strip()
        base_slug = _slugify(name)
        candidate = base_slug
        suffix = 2
        while candidate in used_slugs:
            candidate = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(candidate)
        bind.execute(
            sa.text("UPDATE organizations SET slug = :slug WHERE id = :org_id"),
            {"slug": candidate, "org_id": org_id},
        )


def _migrate_membership_roles(bind) -> None:
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE membership_role RENAME TO membership_role_old")
        op.execute("CREATE TYPE membership_role AS ENUM ('OWNER', 'ADMIN', 'PROVIDER', 'STAFF')")
        op.execute(
            """
            ALTER TABLE organization_memberships
            ALTER COLUMN role TYPE membership_role
            USING (
                CASE role::text
                    WHEN 'MANAGER' THEN 'ADMIN'
                    WHEN 'ASSISTANT' THEN 'PROVIDER'
                    ELSE role::text
                END
            )::membership_role
            """
        )
        op.execute("DROP TYPE membership_role_old")
    else:
        op.execute("UPDATE organization_memberships SET role = 'ADMIN' WHERE role = 'MANAGER'")
        op.execute("UPDATE organization_memberships SET role = 'PROVIDER' WHERE role = 'ASSISTANT'")


def upgrade() -> None:
    op.add_column("organizations", sa.Column("slug", sa.String(length=255), nullable=True))

    bind = op.get_bind()
    _backfill_organization_slugs(bind)
    op.alter_column("organizations", "slug", existing_type=sa.String(length=255), nullable=False)
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    _rename_membership_table_if_needed(bind)

    if bind.dialect.name != "sqlite":
        inspector = sa.inspect(bind)
        constraints = {item["name"] for item in inspector.get_unique_constraints("organization_memberships")}
        if "uq_org_member_org_user" in constraints:
            op.drop_constraint("uq_org_member_org_user", "organization_memberships", type_="unique")
        constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("organization_memberships")}
        if "uq_org_membership_org_user" not in constraints:
            op.create_unique_constraint(
                "uq_org_membership_org_user",
                "organization_memberships",
                ["organization_id", "user_id"],
            )

    _migrate_membership_roles(bind)


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE membership_role RENAME TO membership_role_new")
        op.execute("CREATE TYPE membership_role AS ENUM ('OWNER', 'MANAGER', 'STAFF', 'ASSISTANT')")
        op.execute(
            """
            ALTER TABLE organization_memberships
            ALTER COLUMN role TYPE membership_role
            USING (
                CASE role::text
                    WHEN 'ADMIN' THEN 'MANAGER'
                    WHEN 'PROVIDER' THEN 'ASSISTANT'
                    ELSE role::text
                END
            )::membership_role
            """
        )
        op.execute("DROP TYPE membership_role_new")
    else:
        op.execute("UPDATE organization_memberships SET role = 'MANAGER' WHERE role = 'ADMIN'")
        op.execute("UPDATE organization_memberships SET role = 'ASSISTANT' WHERE role = 'PROVIDER'")

    if bind.dialect.name != "sqlite":
        constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("organization_memberships")}
        if "uq_org_membership_org_user" in constraints:
            op.drop_constraint("uq_org_membership_org_user", "organization_memberships", type_="unique")
        constraints = {item["name"] for item in sa.inspect(bind).get_unique_constraints("organization_memberships")}
        if "uq_org_member_org_user" not in constraints:
            op.create_unique_constraint(
                "uq_org_member_org_user",
                "organization_memberships",
                ["organization_id", "user_id"],
            )

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "organization_memberships" in tables and "organization_members" not in tables:
        op.rename_table("organization_memberships", "organization_members")

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_column("organizations", "slug")
