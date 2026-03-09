import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.provider import Provider
from app.models.service import Service


def test_provider_duration_db_constraint(db_session: Session) -> None:
    organization = Organization(
        name="Constraint Org",
        business_type="clinic",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    db_session.add(organization)
    db_session.commit()
    db_session.refresh(organization)

    bad_provider = Provider(
        organization_id=organization.id,
        display_name="Bad Provider",
        appointment_duration_minutes=0,
        is_active=True,
    )
    db_session.add(bad_provider)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_service_price_and_duration_db_constraints(db_session: Session) -> None:
    organization = Organization(
        name="Constraint Service Org",
        business_type="salon",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    db_session.add(organization)
    db_session.commit()
    db_session.refresh(organization)

    bad_service = Service(
        organization_id=organization.id,
        name="Bad Service",
        duration_minutes=0,
        price=-5,
        is_active=True,
    )
    db_session.add(bad_service)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
