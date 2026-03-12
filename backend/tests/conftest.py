from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.observability.metrics import reset_metrics_for_tests
from app.services.rate_limiter import rate_limiter

SQLALCHEMY_DATABASE_URL = "sqlite+pysqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def seeded_user(db_session: Session) -> User:
    user = User(
        email="owner@test.local",
        hashed_password=get_password_hash("password123"),
        full_name="Test Owner",
        is_active=True,
        is_platform_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def auth_headers(client: TestClient, seeded_user: User) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": seeded_user.email, "password": "password123"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "access_token" in payload, payload
    token = payload["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function", autouse=True)
def stub_celery_send_task(monkeypatch):
    monkeypatch.setattr(
        "app.services.notifications.dispatcher.celery_app.send_task",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.workers.tasks.celery_app.send_task",
        lambda *args, **kwargs: None,
    )


@pytest.fixture(scope="function", autouse=True)
def reset_observability_metrics():
    reset_metrics_for_tests()


@pytest.fixture(scope="function", autouse=True)
def reset_rate_limiter_state():
    rate_limiter.reset_for_tests()
