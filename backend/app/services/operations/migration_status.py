from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _get_head_revisions() -> list[str]:
    project_root = _project_root()
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "alembic"))
    script = ScriptDirectory.from_config(config)
    return sorted(script.get_heads())


def _get_current_revisions(db: Session) -> list[str]:
    rows = db.execute(text("SELECT version_num FROM alembic_version")).all()
    return sorted(str(row[0]) for row in rows if row and row[0])


def get_migration_status(db: Session) -> dict[str, object]:
    try:
        head_revisions = _get_head_revisions()
    except Exception as exc:
        return {
            "status": "unknown",
            "up_to_date": False,
            "head_revisions": [],
            "current_revisions": [],
            "pending_revisions": [],
            "error": f"head_lookup_failed:{exc.__class__.__name__}",
        }

    try:
        current_revisions = _get_current_revisions(db)
    except Exception as exc:
        return {
            "status": "unknown",
            "up_to_date": False,
            "head_revisions": head_revisions,
            "current_revisions": [],
            "pending_revisions": head_revisions,
            "error": f"current_lookup_failed:{exc.__class__.__name__}",
        }

    pending_revisions = [rev for rev in head_revisions if rev not in set(current_revisions)]
    up_to_date = not pending_revisions and bool(head_revisions)
    return {
        "status": "up_to_date" if up_to_date else "outdated",
        "up_to_date": up_to_date,
        "head_revisions": head_revisions,
        "current_revisions": current_revisions,
        "pending_revisions": pending_revisions,
        "error": None,
    }
