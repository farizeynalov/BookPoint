from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_platform_admin
from app.models.organization import Organization
from app.models.user import User
from app.schemas.admin import AdminPing

router = APIRouter()


@router.get("/ping", response_model=AdminPing)
def admin_ping(_: User = Depends(require_platform_admin)) -> AdminPing:
    return AdminPing(status="admin_ok")


@router.get("/stats")
def admin_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_platform_admin),
) -> dict[str, int]:
    organizations_count = db.scalar(select(func.count(Organization.id))) or 0
    return {"organizations_count": organizations_count}
