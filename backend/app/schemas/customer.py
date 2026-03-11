from app.schemas.common import ORMModel, TimestampRead


class CustomerBase(ORMModel):
    full_name: str
    phone_number: str
    email: str | None = None
    preferred_language: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(ORMModel):
    full_name: str | None = None
    phone_number: str | None = None
    email: str | None = None
    preferred_language: str | None = None


class CustomerRead(CustomerBase, TimestampRead):
    id: int
