from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_admin_membership,
    require_org_membership,
)
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.organization_member_repository import OrganizationMemberRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.provider_service_repository import ProviderServiceRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.provider_service import (
    ProviderAssignedServiceRead,
    ProviderServiceAssignCreate,
)
from app.schemas.service import ProviderServiceCreate, ServiceCreate, ServiceRead, ServiceUpdate

router = APIRouter()
provider_services_router = APIRouter()


def _build_assigned_service_read(service, assignment) -> ProviderAssignedServiceRead:
    effective_duration_minutes = assignment.duration_minutes_override or service.duration_minutes
    payload = {
        **ServiceRead.model_validate(service).model_dump(),
        "provider_id": assignment.provider_id,
        "duration_minutes_override": assignment.duration_minutes_override,
        "effective_duration_minutes": effective_duration_minutes,
    }
    return ProviderAssignedServiceRead.model_validate(payload)


def _require_provider_service_read_access(db: Session, *, provider, user: User) -> None:
    membership = require_org_membership(db, organization_id=provider.organization_id, user=user)
    if user.is_platform_admin:
        return
    if membership.role == MembershipRole.PROVIDER and provider.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization role")


@provider_services_router.post("/{provider_id}/services", response_model=ProviderAssignedServiceRead, status_code=status.HTTP_201_CREATED)
def create_provider_service(
    provider_id: int,
    payload: ProviderServiceAssignCreate | ProviderServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ProviderAssignedServiceRead:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    service_repo = ServiceRepository(db)
    provider_service_repo = ProviderServiceRepository(db)
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
    if isinstance(payload, ProviderServiceAssignCreate):
        service = service_repo.get(payload.service_id)
        if service is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        if service.organization_id != provider.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider and service organization mismatch")
        existing = provider_service_repo.get_by_provider_and_service(provider_id=provider.id, service_id=service.id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider already assigned to this service")
        assignment = provider_service_repo.create(
            provider_id=provider.id,
            service_id=service.id,
            duration_minutes_override=payload.duration_minutes_override,
        )
        return _build_assigned_service_read(service, assignment)

    create_data = payload.model_dump()
    try:
        service = service_repo.create(
            organization_id=provider.organization_id,
            provider_id=provider.id,
            **create_data,
        )
        assignment = provider_service_repo.create(
            provider_id=provider.id,
            service_id=service.id,
            duration_minutes_override=None,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service failed integrity checks")
    return _build_assigned_service_read(service, assignment)


@provider_services_router.get("/{provider_id}/services", response_model=list[ProviderAssignedServiceRead])
def list_provider_services(
    provider_id: int,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ProviderAssignedServiceRead]:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    _require_provider_service_read_access(db, provider=provider, user=current_user)
    assignments = ProviderServiceRepository(db).list_by_provider(
        provider_id=provider_id,
        include_inactive_services=include_inactive,
    )
    return [_build_assigned_service_read(assignment.service, assignment) for assignment in assignments]


@provider_services_router.delete("/{provider_id}/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_provider_service(
    provider_id: int,
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
    assignment = ProviderServiceRepository(db).get_by_provider_and_service(provider_id=provider_id, service_id=service_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider-service assignment not found")
    ProviderServiceRepository(db).delete(assignment)


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    provider_repo = ProviderRepository(db)
    provider_service_repo = ProviderServiceRepository(db)
    service_repo = ServiceRepository(db)

    provider = provider_repo.get(payload.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    if provider.organization_id != payload.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider org mismatch")

    require_org_admin_membership(db, organization_id=payload.organization_id, user=current_user)
    create_data = payload.model_dump()
    try:
        service = service_repo.create(**create_data)
        existing_assignment = provider_service_repo.get_by_provider_and_service(
            provider_id=provider.id,
            service_id=service.id,
        )
        if existing_assignment is None:
            provider_service_repo.create(
                provider_id=provider.id,
                service_id=service.id,
                duration_minutes_override=None,
            )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service failed integrity checks")
    return ServiceRead.model_validate(service)


@router.get("", response_model=list[ServiceRead])
def list_services(
    organization_id: int | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    include_inactive: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ServiceRead]:
    service_repo = ServiceRepository(db)
    if organization_id is not None:
        require_org_membership(db, organization_id=organization_id, user=current_user)
        services = service_repo.list_services(
            organization_id=organization_id,
            provider_id=provider_id,
            include_inactive=include_inactive,
        )
    elif current_user.is_platform_admin:
        services = service_repo.list_services(
            provider_id=provider_id,
            include_inactive=include_inactive,
        )
    else:
        org_ids = OrganizationMemberRepository(db).list_active_org_ids_for_user(current_user.id)
        if not org_ids:
            return []
        services = [
            service
            for service in service_repo.list_services(provider_id=provider_id, include_inactive=include_inactive)
            if service.organization_id in org_ids
        ]
    return [ServiceRead.model_validate(service) for service in services]


@router.get("/{service_id}", response_model=ServiceRead)
def get_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    service = ServiceRepository(db).get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    require_org_membership(db, organization_id=service.organization_id, user=current_user)
    return ServiceRead.model_validate(service)


@router.patch("/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: int,
    payload: ServiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    service_repo = ServiceRepository(db)
    provider_repo = ProviderRepository(db)
    provider_service_repo = ProviderServiceRepository(db)
    service = service_repo.get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)
    updates = payload.model_dump(exclude_unset=True)
    if "provider_id" in updates:
        provider_id = updates["provider_id"]
        if provider_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider_id cannot be null")
        provider = provider_repo.get(provider_id)
        if provider is None or provider.organization_id != service.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider assignment")
    try:
        updated = service_repo.update(service, **updates)
        if "provider_id" in updates:
            assignment = provider_service_repo.get_by_provider_and_service(
                provider_id=updated.provider_id,
                service_id=updated.id,
            )
            if assignment is None:
                provider_service_repo.create(
                    provider_id=updated.provider_id,
                    service_id=updated.id,
                    duration_minutes_override=None,
                )
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service failed integrity checks")
    return ServiceRead.model_validate(updated)


@router.post("/{service_id}/activate", response_model=ServiceRead)
def activate_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    service_repo = ServiceRepository(db)
    service = service_repo.get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)
    updated = service_repo.update(service, is_active=True)
    return ServiceRead.model_validate(updated)


@router.post("/{service_id}/deactivate", response_model=ServiceRead)
def deactivate_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    service_repo = ServiceRepository(db)
    service = service_repo.get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)
    updated = service_repo.update(service, is_active=False)
    return ServiceRead.model_validate(updated)


@router.delete("/{service_id}", response_model=ServiceRead)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    service_repo = ServiceRepository(db)
    service = service_repo.get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)
    updated = service_repo.update(service, is_active=False)
    return ServiceRead.model_validate(updated)
