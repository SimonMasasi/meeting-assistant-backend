"""
Test fixtures shared across the whole test suite.

Import order matters:
  1. Root conftest.py already set DATABASE_URL / SECRET_KEY in os.environ.
  2. We patch run_migrations before importing `app` so the Alembic call is
     skipped (SQLite doesn't need Alembic).
  3. After the import we create all tables via SQLModel metadata.
"""
import pytest
from unittest.mock import patch
from sqlmodel import SQLModel, Session
from fastapi.testclient import TestClient

# Patch Alembic migration runner before app.py runs it at module-import time.
with patch("src.shared.database.run_migrations", return_value=None):
    from app import app  # noqa: E402  (import after env-var setup)

from src.shared.database import engine
from src.shared.dependencies import get_current_user
from src.modules.auth.models import User
from src.utils.passwords import PasswordManager
from src.utils.generators import Generator

# ---------------------------------------------------------------------------
# DB bootstrap
# ---------------------------------------------------------------------------

SQLModel.metadata.create_all(engine)

_password_manager = PasswordManager()

TEST_PASSWORD = "Test@1234"


def _build_user(**overrides) -> User:
    defaults = {
        "id": Generator.generate_64bit_int_uuid(),
        "username": "testuser",
        "email": "test@example.com",
        "password": _password_manager.hash_password(TEST_PASSWORD),
    }
    defaults.update(overrides)
    return User(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_db():
    """Wipe and recreate all tables before every test for full isolation."""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    # teardown – nothing extra needed; next test's autouse fixture handles it


@pytest.fixture
def db_session():
    """Yields an open SQLModel session backed by the test SQLite engine."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    """Bare TestClient – no auth overrides applied."""
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def user(db_session) -> User:
    """A persisted User row available for tests that need an existing user."""
    u = _build_user()
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def second_user(db_session) -> User:
    """A second distinct user for isolation / ownership tests."""
    u = _build_user(
        id=Generator.generate_64bit_int_uuid(),
        username="otheruser",
        email="other@example.com",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture
def auth_client(client: TestClient, user: User) -> TestClient:
    """TestClient whose get_current_user dependency is overridden to return
    the ``user`` fixture – no real JWT is needed."""
    app.dependency_overrides[get_current_user] = lambda: user
    yield client
    app.dependency_overrides.clear()
