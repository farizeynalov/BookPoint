from datetime import datetime

from pydantic import EmailStr

from app.schemas.common import ORMModel


class LoginRequest(ORMModel):
    email: EmailStr
    password: str


class TokenResponse(ORMModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(ORMModel):
    id: int
    email: EmailStr
    full_name: str
    phone_number: str | None
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    updated_at: datetime
