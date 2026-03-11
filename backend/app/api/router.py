from fastapi import APIRouter

from app.api.routers import (
    admin,
    appointments,
    auth,
    customer_identities,
    customers,
    organizations,
    organization_members,
    provider_availability,
    provider_date_overrides,
    provider_time_off,
    providers,
    scheduling,
    services,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])
api_router.include_router(
    organization_members.nested_router,
    prefix="/organizations",
    tags=["organization-memberships"],
)
api_router.include_router(organization_members.router, prefix="/organization-members", tags=["organization-members"])
api_router.include_router(providers.router, prefix="/providers", tags=["providers"])
api_router.include_router(services.provider_services_router, prefix="/providers", tags=["services"])
api_router.include_router(provider_availability.provider_scoped_router, prefix="/providers", tags=["provider-availability"])
api_router.include_router(provider_time_off.provider_scoped_router, prefix="/providers", tags=["provider-time-off"])
api_router.include_router(provider_date_overrides.provider_scoped_router, prefix="/providers", tags=["provider-date-overrides"])
api_router.include_router(services.router, prefix="/services", tags=["services"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(customer_identities.router, prefix="/customer-identities", tags=["customer-identities"])
api_router.include_router(provider_availability.router, prefix="/provider-availability", tags=["provider-availability"])
api_router.include_router(provider_time_off.router, prefix="/provider-time-off", tags=["provider-time-off"])
api_router.include_router(provider_date_overrides.router, prefix="/provider-date-overrides", tags=["provider-date-overrides"])
api_router.include_router(scheduling.router, prefix="/scheduling", tags=["scheduling"])
api_router.include_router(appointments.router, prefix="/appointments", tags=["appointments"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
