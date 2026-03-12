from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.provider_repository import ProviderRepository
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentRead,
    AppointmentReschedule,
)
from app.services.appointment_service import AppointmentService

router = APIRouter()


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AppointmentRead:
    provider = ProviderRepository(db).get(payload.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_membership(db, organization_id=provider.organization_id, user=current_user)
    appointment_service = AppointmentService(db)
    try:
        appointment = appointment_service.create_appointment(
            payload,
            actor_type="user",
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment constraint conflict")
    return AppointmentRead.model_validate(appointment)


@router.get("", response_model=list[AppointmentRead])
def list_appointments(
    organization_id: int | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    customer_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[AppointmentRead]:
    appointment_repo = AppointmentRepository(db)
    rows = []
    if organization_id is not None:
        require_org_membership(db, organization_id=organization_id, user=current_user)
        rows = appointment_repo.list_appointments(
            organization_id=organization_id,
            provider_id=provider_id,
            customer_id=customer_id,
        )
    elif current_user.is_platform_admin:
        rows = appointment_repo.list_appointments(provider_id=provider_id, customer_id=customer_id)
    else:
        org_ids = OrganizationMemberRepository(db).list_active_org_ids_for_user(current_user.id)
        rows = appointment_repo.list_by_organization_ids(org_ids)
        if provider_id is not None:
            rows = [row for row in rows if row.provider_id == provider_id]
        if customer_id is not None:
            rows = [row for row in rows if row.customer_id == customer_id]
    return [AppointmentRead.model_validate(row) for row in rows]


@router.get("/{appointment_id}", response_model=AppointmentRead)
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AppointmentRead:
    appointment = AppointmentRepository(db).get(appointment_id)
    if appointment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    require_org_membership(db, organization_id=appointment.organization_id, user=current_user)
    return AppointmentRead.model_validate(appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    appointment_id: int,
    payload: AppointmentCancel,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AppointmentRead:
    appointment_repo = AppointmentRepository(db)
    existing = appointment_repo.get(appointment_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    require_org_membership(db, organization_id=existing.organization_id, user=current_user)

    try:
        updated = AppointmentService(db).cancel_appointment(
            appointment_id,
            notes=payload.notes,
            actor_type="user",
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return AppointmentRead.model_validate(updated)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentRead)
def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AppointmentRead:
    appointment_repo = AppointmentRepository(db)
    existing = appointment_repo.get(appointment_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    require_org_membership(db, organization_id=existing.organization_id, user=current_user)

    try:
        updated = AppointmentService(db).reschedule_appointment(
            appointment_id,
            payload.start_datetime,
            actor_type="user",
            actor_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Appointment constraint conflict")
    return AppointmentRead.model_validate(updated)
