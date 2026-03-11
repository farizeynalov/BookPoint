from sqlalchemy import select
from sqlalchemy.orm import Session

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
