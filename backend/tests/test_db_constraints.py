import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.provider import Provider
from app.models.service import Service


def test_provider_duration_db_constraint(db_session: Session) -> None:
    organization = Organization(
        name="Constraint Org",
        slug="constraint-org",
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
        slug="constraint-service-org",
        business_type="salon",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    db_session.add(organization)
    db_session.commit()
    db_session.refresh(organization)

    provider = Provider(
        organization_id=organization.id,
        display_name="Constraint Provider",
        appointment_duration_minutes=30,
        is_active=True,
    )
    db_session.add(provider)
    db_session.commit()
    db_session.refresh(provider)

    bad_service = Service(
        organization_id=organization.id,
        provider_id=provider.id,
        name="Bad Service",
        duration_minutes=0,
        price=-5,
        is_active=True,
    )
    db_session.add(bad_service)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_service_buffer_db_constraints(db_session: Session) -> None:
    organization = Organization(
        name="Constraint Buffer Org",
        slug="constraint-buffer-org",
        business_type="salon",
        city="Baku",
        timezone="Asia/Baku",
        is_active=True,
    )
    db_session.add(organization)
    db_session.commit()
    db_session.refresh(organization)

    provider = Provider(
        organization_id=organization.id,
        display_name="Buffer Constraint Provider",
        appointment_duration_minutes=30,
        is_active=True,
    )
    db_session.add(provider)
    db_session.commit()
    db_session.refresh(provider)

    bad_service = Service(
        organization_id=organization.id,
        provider_id=provider.id,
        name="Bad Buffer Service",
        duration_minutes=30,
        price=10,
        buffer_before_minutes=-1,
        buffer_after_minutes=0,
        is_active=True,
    )
    db_session.add(bad_service)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
