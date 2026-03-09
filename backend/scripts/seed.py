from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.appointment import Appointment
from app.models.customer import Customer
from app.models.customer_channel_identity import CustomerChannelIdentity
from app.models.enums import AppointmentStatus, BookingChannel, ChannelType, MembershipRole
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.provider import Provider
from app.models.provider_availability import ProviderAvailability
from app.models.service import Service
from app.models.user import User
from app.utils.phone import normalize_phone_number


def as_utc(local_dt: datetime, tz_name: str) -> datetime:
    return local_dt.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)


def seed() -> None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.email == "admin@bookpoint.local"))
        if admin is None:
            admin = User(
                email="admin@bookpoint.local",
                hashed_password=get_password_hash("admin123"),
                full_name="Platform Admin",
                is_active=True,
                is_platform_admin=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)

        org_one = db.scalar(select(Organization).where(Organization.name == "BookPoint Demo Clinic"))
        if org_one is None:
            org_one = Organization(
                name="BookPoint Demo Clinic",
                business_type="clinic",
                city="Baku",
                address="Nizami Street 123",
                timezone="Asia/Baku",
                is_active=True,
            )
            db.add(org_one)
            db.commit()
            db.refresh(org_one)

        org_two = db.scalar(select(Organization).where(Organization.name == "BookPoint Demo Salon"))
        if org_two is None:
            org_two = Organization(
                name="BookPoint Demo Salon",
                business_type="salon",
                city="Baku",
                address="Tbilisi Avenue 45",
                timezone="Asia/Baku",
                is_active=True,
            )
            db.add(org_two)
            db.commit()
            db.refresh(org_two)

        owner = db.scalar(select(User).where(User.email == "owner@demo.local"))
        if owner is None:
            owner = User(
                email="owner@demo.local",
                hashed_password=get_password_hash("owner123"),
                full_name="Demo Owner",
                is_active=True,
                is_platform_admin=False,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)

        owner_membership = db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_one.id,
                OrganizationMember.user_id == owner.id,
            )
        )
        if owner_membership is None:
            db.add(
                OrganizationMember(
                    organization_id=org_one.id,
                    user_id=owner.id,
                    role=MembershipRole.OWNER,
                    is_active=True,
                )
            )
            db.commit()

        provider = db.scalar(select(Provider).where(Provider.display_name == "Dr. Leyla Mammadova"))
        if provider is None:
            provider = Provider(
                organization_id=org_one.id,
                display_name="Dr. Leyla Mammadova",
                title="General Practitioner",
                appointment_duration_minutes=30,
                is_active=True,
            )
            db.add(provider)
            db.commit()
            db.refresh(provider)

        salon_provider = db.scalar(select(Provider).where(Provider.display_name == "Nigar Stylist"))
        if salon_provider is None:
            salon_provider = Provider(
                organization_id=org_two.id,
                display_name="Nigar Stylist",
                title="Senior Hair Stylist",
                appointment_duration_minutes=45,
                is_active=True,
            )
            db.add(salon_provider)
            db.commit()
            db.refresh(salon_provider)

        consult_service = db.scalar(select(Service).where(Service.name == "General Consultation"))
        if consult_service is None:
            consult_service = Service(
                organization_id=org_one.id,
                provider_id=provider.id,
                name="General Consultation",
                duration_minutes=30,
                price=50,
                is_active=True,
            )
            db.add(consult_service)
            db.commit()
            db.refresh(consult_service)

        haircut_service = db.scalar(select(Service).where(Service.name == "Haircut"))
        if haircut_service is None:
            haircut_service = Service(
                organization_id=org_two.id,
                provider_id=salon_provider.id,
                name="Haircut",
                duration_minutes=45,
                price=30,
                is_active=True,
            )
            db.add(haircut_service)
            db.commit()
            db.refresh(haircut_service)

        customer = db.scalar(select(Customer).where(Customer.phone_number == "+994501112233"))
        if customer is None:
            customer = Customer(
                full_name="Aysel Aliyeva",
                phone_number="+994501112233",
                phone_number_normalized=normalize_phone_number("+994501112233"),
                email="aysel@example.com",
                preferred_language="az",
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)

        web_identity = db.scalar(
            select(CustomerChannelIdentity).where(
                CustomerChannelIdentity.customer_id == customer.id,
                CustomerChannelIdentity.channel == ChannelType.WEB,
                CustomerChannelIdentity.external_user_id == "web-aysel-1",
            )
        )
        if web_identity is None:
            db.add(
                CustomerChannelIdentity(
                    customer_id=customer.id,
                    channel=ChannelType.WEB,
                    external_user_id="web-aysel-1",
                    external_chat_id=None,
                )
            )
            db.commit()

        availability_exists = db.scalar(
            select(ProviderAvailability).where(
                ProviderAvailability.provider_id == provider.id,
                ProviderAvailability.weekday == 0,
                ProviderAvailability.start_time == time(9, 0),
                ProviderAvailability.end_time == time(17, 0),
            )
        )
        if availability_exists is None:
            db.add(
                ProviderAvailability(
                    provider_id=provider.id,
                    weekday=0,
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    is_active=True,
                )
            )
            db.commit()

        today = date.today()
        next_monday = today + timedelta(days=(7 - today.weekday()) % 7)
        appointment_start_local = datetime.combine(next_monday, time(10, 0))
        appointment_start = as_utc(appointment_start_local, org_one.timezone)
        appointment_end = appointment_start + timedelta(minutes=30)

        existing_appointment = db.scalar(
            select(Appointment).where(
                Appointment.provider_id == provider.id,
                Appointment.customer_id == customer.id,
                Appointment.start_datetime == appointment_start,
            )
        )
        if existing_appointment is None:
            db.add(
                Appointment(
                    organization_id=org_one.id,
                    provider_id=provider.id,
                    service_id=consult_service.id,
                    customer_id=customer.id,
                    start_datetime=appointment_start,
                    end_datetime=appointment_end,
                    status=AppointmentStatus.CONFIRMED,
                    booking_channel=BookingChannel.DASHBOARD,
                    notes="Seed appointment",
                )
            )
            db.commit()

        print("Seed completed successfully.")
        print("Admin login: admin@bookpoint.local / admin123")
        print("Owner login: owner@demo.local / owner123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
