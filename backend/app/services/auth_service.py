from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def authenticate_user(self, *, email: str, password: str) -> User | None:
        user = self.user_repo.get_by_email(email=email)
        if user is None:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
