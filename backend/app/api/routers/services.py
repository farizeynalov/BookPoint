from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user, require_org_membership
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.service import ServiceCreate, ServiceRead, ServiceUpdate

router = APIRouter()


@router.post("", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> ServiceRead:
    org_repo = OrganizationRepository(db)
    provider_repo = ProviderRepository(db)
    service_repo = ServiceRepository(db)

    organization = org_repo.get(payload.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if payload.provider_id is not None:
        provider = provider_repo.get(payload.provider_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
        if provider.organization_id != payload.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider org mismatch")

    require_org_membership(db, organization_id=payload.organization_id, user=current_user)
    try:
        service = service_repo.create(**payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service failed integrity checks")
    return ServiceRead.model_validate(service)


@router.get("", response_model=list[ServiceRead])
def list_services(
    organization_id: int | None = Query(default=None),
    provider_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[ServiceRead]:
    if organization_id is not None:
        require_org_membership(db, organization_id=organization_id, user=current_user)
    services = ServiceRepository(db).list_services(organization_id=organization_id, provider_id=provider_id)
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
    service = service_repo.get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")

    require_org_membership(db, organization_id=service.organization_id, user=current_user)
    updates = payload.model_dump(exclude_unset=True)
    if "provider_id" in updates and updates["provider_id"] is not None:
        provider = provider_repo.get(updates["provider_id"])
        if provider is None or provider.organization_id != service.organization_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid provider assignment")
    try:
        updated = service_repo.update(service, **updates)
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
    require_org_membership(db, organization_id=service.organization_id, user=current_user)
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
    require_org_membership(db, organization_id=service.organization_id, user=current_user)
    updated = service_repo.update(service, is_active=False)
    return ServiceRead.model_validate(updated)
