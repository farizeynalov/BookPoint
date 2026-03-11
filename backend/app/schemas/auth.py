from datetime import datetime

from app.schemas.common import ORMModel


class LoginRequest(ORMModel):
    email: str
    password: str


class TokenResponse(ORMModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserRead(ORMModel):
    id: int
    email: str
    full_name: str
    phone_number: str | None
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    updated_at: datetime
