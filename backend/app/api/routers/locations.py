from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import (
    get_current_active_user,
    require_org_admin_membership,
    require_org_membership,
)
from app.models.enums import MembershipRole
from app.models.user import User
from app.repositories.organization_location_repository import OrganizationLocationRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.provider_location_repository import ProviderLocationRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.service_location_repository import ServiceLocationRepository
from app.repositories.service_repository import ServiceRepository
from app.schemas.organization_location import (
    LocationAssignmentCreate,
    OrganizationLocationCreate,
    OrganizationLocationRead,
    OrganizationLocationUpdate,
)

organization_locations_router = APIRouter()
provider_locations_router = APIRouter()
service_locations_router = APIRouter()


def _get_organization_or_404(db: Session, organization_id: int):
    organization = OrganizationRepository(db).get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


def _get_provider_or_404(db: Session, provider_id: int):
    provider = ProviderRepository(db).get(provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


def _get_service_or_404(db: Session, service_id: int):
    service = ServiceRepository(db).get(service_id)
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return service


def _require_provider_location_read_access(db: Session, *, provider, user: User) -> None:
    membership = require_org_membership(db, organization_id=provider.organization_id, user=user)
    if user.is_platform_admin:
        return
    if membership.role == MembershipRole.PROVIDER and provider.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organization role")


@organization_locations_router.post(
    "/{organization_id}/locations",
    response_model=OrganizationLocationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_location(
    organization_id: int,
    payload: OrganizationLocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationLocationRead:
    _get_organization_or_404(db, organization_id)
    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    location = OrganizationLocationRepository(db).create(
        organization_id=organization_id,
        **payload.model_dump(),
    )
    return OrganizationLocationRead.model_validate(location)


@organization_locations_router.get("/{organization_id}/locations", response_model=list[OrganizationLocationRead])
def list_organization_locations(
    organization_id: int,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationLocationRead]:
    _get_organization_or_404(db, organization_id)
    require_org_membership(db, organization_id=organization_id, user=current_user)
    locations = OrganizationLocationRepository(db).list_by_organization(
        organization_id,
        include_inactive=include_inactive,
    )
    return [OrganizationLocationRead.model_validate(location) for location in locations]


@organization_locations_router.get("/{organization_id}/locations/{location_id}", response_model=OrganizationLocationRead)
def get_organization_location(
    organization_id: int,
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationLocationRead:
    _get_organization_or_404(db, organization_id)
    require_org_membership(db, organization_id=organization_id, user=current_user)
    location = OrganizationLocationRepository(db).get_by_org_and_id(organization_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return OrganizationLocationRead.model_validate(location)


@organization_locations_router.patch("/{organization_id}/locations/{location_id}", response_model=OrganizationLocationRead)
def update_organization_location(
    organization_id: int,
    location_id: int,
    payload: OrganizationLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationLocationRead:
    _get_organization_or_404(db, organization_id)
    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    location_repo = OrganizationLocationRepository(db)
    location = location_repo.get_by_org_and_id(organization_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    updated = location_repo.update(location, **payload.model_dump(exclude_unset=True))
    return OrganizationLocationRead.model_validate(updated)


@organization_locations_router.delete("/{organization_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_organization_location(
    organization_id: int,
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    _get_organization_or_404(db, organization_id)
    require_org_admin_membership(db, organization_id=organization_id, user=current_user)
    location_repo = OrganizationLocationRepository(db)
    location = location_repo.get_by_org_and_id(organization_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if location.is_active:
        location_repo.update(location, is_active=False)


@provider_locations_router.post(
    "/{provider_id}/locations",
    response_model=OrganizationLocationRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_provider_location(
    provider_id: int,
    payload: LocationAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationLocationRead:
    provider = _get_provider_or_404(db, provider_id)
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)

    location = OrganizationLocationRepository(db).get(payload.location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if not location.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found or inactive")
    if location.organization_id != provider.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider and location organization mismatch")

    provider_location_repo = ProviderLocationRepository(db)
    existing = provider_location_repo.get_by_provider_and_location(provider.id, location.id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Provider already assigned to this location")
    provider_location_repo.create(provider_id=provider.id, location_id=location.id)
    return OrganizationLocationRead.model_validate(location)


@provider_locations_router.get("/{provider_id}/locations", response_model=list[OrganizationLocationRead])
def list_provider_locations(
    provider_id: int,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationLocationRead]:
    provider = _get_provider_or_404(db, provider_id)
    _require_provider_location_read_access(db, provider=provider, user=current_user)
    assignments = ProviderLocationRepository(db).list_by_provider(
        provider_id,
        include_inactive_locations=include_inactive,
    )
    return [OrganizationLocationRead.model_validate(assignment.location) for assignment in assignments]


@provider_locations_router.delete("/{provider_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_provider_location(
    provider_id: int,
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    provider = _get_provider_or_404(db, provider_id)
    require_org_admin_membership(db, organization_id=provider.organization_id, user=current_user)
    provider_location_repo = ProviderLocationRepository(db)
    assignment = provider_location_repo.get_by_provider_and_location(provider_id, location_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider-location assignment not found")
    provider_location_repo.delete(assignment)


@service_locations_router.post(
    "/{service_id}/locations",
    response_model=OrganizationLocationRead,
    status_code=status.HTTP_201_CREATED,
)
def assign_service_location(
    service_id: int,
    payload: LocationAssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> OrganizationLocationRead:
    service = _get_service_or_404(db, service_id)
    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)

    location = OrganizationLocationRepository(db).get(payload.location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if not location.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found or inactive")
    if location.organization_id != service.organization_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service and location organization mismatch")

    service_location_repo = ServiceLocationRepository(db)
    existing = service_location_repo.get_by_service_and_location(service.id, location.id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Service already assigned to this location")
    service_location_repo.create(service_id=service.id, location_id=location.id)
    return OrganizationLocationRead.model_validate(location)


@service_locations_router.get("/{service_id}/locations", response_model=list[OrganizationLocationRead])
def list_service_locations(
    service_id: int,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[OrganizationLocationRead]:
    service = _get_service_or_404(db, service_id)
    require_org_membership(db, organization_id=service.organization_id, user=current_user)
    assignments = ServiceLocationRepository(db).list_by_service(
        service_id,
        include_inactive_locations=include_inactive,
    )
    return [OrganizationLocationRead.model_validate(assignment.location) for assignment in assignments]


@service_locations_router.delete("/{service_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_service_location(
    service_id: int,
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    service = _get_service_or_404(db, service_id)
    require_org_admin_membership(db, organization_id=service.organization_id, user=current_user)
    service_location_repo = ServiceLocationRepository(db)
    assignment = service_location_repo.get_by_service_and_location(service_id, location_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service-location assignment not found")
    service_location_repo.delete(assignment)
