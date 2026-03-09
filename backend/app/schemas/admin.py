from app.schemas.common import ORMModel


class AdminPing(ORMModel):
    status: str
