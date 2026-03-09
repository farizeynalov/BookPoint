from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_active_user
from app.models.user import User
from app.repositories.customer_identity_repository import CustomerIdentityRepository
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer_channel_identity import CustomerChannelIdentityCreate, CustomerChannelIdentityRead

router = APIRouter()


@router.post("", response_model=CustomerChannelIdentityRead, status_code=status.HTTP_201_CREATED)
def create_identity(
    payload: CustomerChannelIdentityCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> CustomerChannelIdentityRead:
    customer_repo = CustomerRepository(db)
    identity_repo = CustomerIdentityRepository(db)

    if customer_repo.get(payload.customer_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    existing = identity_repo.get_by_channel_external_user(payload.channel, payload.external_user_id)
    if existing and existing.customer_id != payload.customer_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity is already linked to another customer")
    existing_for_customer_channel = identity_repo.get_by_customer_and_channel(payload.customer_id, payload.channel)
    if existing_for_customer_channel:
        if existing_for_customer_channel.external_user_id == payload.external_user_id:
            return CustomerChannelIdentityRead.model_validate(existing_for_customer_channel)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer already has an identity on this channel",
        )

    try:
        identity = identity_repo.create(**payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Identity already linked")
    return CustomerChannelIdentityRead.model_validate(identity)


@router.get("", response_model=list[CustomerChannelIdentityRead])
def list_identities(
    customer_id: int = Query(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> list[CustomerChannelIdentityRead]:
    identities = CustomerIdentityRepository(db).list_by_customer(customer_id)
    return [CustomerChannelIdentityRead.model_validate(identity) for identity in identities]
