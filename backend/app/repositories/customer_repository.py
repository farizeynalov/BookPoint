from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.customer import Customer
from app.utils.phone import normalize_phone_number


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Customer:
        phone_number = kwargs.get("phone_number")
        if phone_number is None:
            raise ValueError("phone_number is required")
        kwargs["phone_number_normalized"] = normalize_phone_number(phone_number)
        customer = Customer(**kwargs)
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def get(self, customer_id: int) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def get_by_phone_normalized(self, phone_number_normalized: str) -> Customer | None:
        stmt = select(Customer).where(Customer.phone_number_normalized == phone_number_normalized).limit(1)
        return self.db.scalar(stmt)

    def list_by_email(self, email: str) -> list[Customer]:
        stmt = (
            select(Customer)
            .where(Customer.email.is_not(None), func.lower(Customer.email) == email.lower())
            .order_by(Customer.id.asc())
        )
        return list(self.db.scalars(stmt))

    def has_appointment_in_organization(self, customer_id: int, organization_id: int) -> bool:
        stmt = select(Appointment.id).where(
            Appointment.customer_id == customer_id,
            Appointment.organization_id == organization_id,
        )
        return self.db.scalar(stmt) is not None

    def list_customers(self) -> list[Customer]:
        stmt = select(Customer).order_by(Customer.id.asc())
        return list(self.db.scalars(stmt))

    def update(self, customer: Customer, **kwargs) -> Customer:
        if "phone_number" in kwargs and kwargs["phone_number"] is not None:
            kwargs["phone_number_normalized"] = normalize_phone_number(kwargs["phone_number"])
        for field, value in kwargs.items():
            setattr(customer, field, value)
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer
