"""Shared test fixtures for console API tests."""

import shutil
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src/console/backend"))

# Production-safety validation (config.validate_production_settings) must see
# strong test secrets when the app is imported with DEBUG=false.
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-value-32bytes-minimum")
os.environ.setdefault("TIMESTAMP_HMAC_KEY", "unit-test-hmac-key-value-32bytes-minimum")

# Keep uploads out of the deployed storage location. config.upload_dir defaults
# to ~/civildx/uploads, which on this host is the *production* upload directory,
# so every document-upload test wrote real files there: it had grown to ~2,000
# PDFs that no database row referenced (700 from a single day of test runs).
# Assigned through os.environ (not a module-level variable) so the setup block
# stays "allowed before imports" for ruff's E402 rule.
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="civilpdf-test-uploads-")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, get_db
from auth.jwt import get_password_hash
from middleware.rate_limit import reset_all
from models.user import User, UserRole, UserStatus

# One SQLite file per pytest process: a shared ./test_console.db let two concurrent
# runs (e.g. a stale background run) drop each other's tables mid-test.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="civilpdf-test-db-")
SQLALCHEMY_TEST_URL = f"sqlite:///{_TEST_DB_DIR}/test_console.db"

engine_test = create_engine(
    SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_isolated_upload_dir():
    """Remove the throwaway upload and DB directories once the session ends."""
    yield
    shutil.rmtree(os.environ.get("UPLOAD_DIR", ""), ignore_errors=True)
    engine_test.dispose()
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_rate_limiter_between_tests():
    """Keep per-IP counters isolated between tests (TestClient shares 127.0.0.1)."""
    reset_all()
    yield
    reset_all()


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="package")
def _override_db():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_user():
    db = TestingSessionLocal()
    user = User(
        email="admin@example.com",
        username="admin",
        full_name="Admin User",
        hashed_password=get_password_hash("Admin1234!"),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture
def admin_token(client, admin_user):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "admin@example.com", "password": "Admin1234!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def inactive_user():
    from auth.jwt import get_password_hash

    db = TestingSessionLocal()
    user = User(
        email="inactive@example.com",
        username="inactive1",
        full_name="Inactive User",
        hashed_password=get_password_hash("Inactive123!"),
        role=UserRole.VIEWER,
        status=UserStatus.INACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture
def viewer_user():
    from auth.jwt import get_password_hash

    db = TestingSessionLocal()
    user = User(
        email="viewer@example.com",
        username="viewer1",
        full_name="Viewer User",
        hashed_password=get_password_hash("Viewer123!"),
        role=UserRole.VIEWER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture
def viewer_token(client, viewer_user):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "viewer@example.com", "password": "Viewer123!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def manager_user():
    from auth.jwt import get_password_hash
    from models.user import UserRole, UserStatus

    db = TestingSessionLocal()
    user = User(
        email="manager@example.com",
        username="manager1",
        full_name="Manager User",
        hashed_password=get_password_hash("Manager123!"),
        role=UserRole.MANAGER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture
def manager_token(client, manager_user):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "manager@example.com", "password": "Manager123!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def engineer_user():
    from auth.jwt import get_password_hash
    from models.user import UserRole, UserStatus

    db = TestingSessionLocal()
    user = User(
        email="engineer@example.com",
        username="engineer1",
        full_name="Engineer User",
        hashed_password=get_password_hash("Engineer123!"),
        role=UserRole.ENGINEER,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


@pytest.fixture
def engineer_token(client, engineer_user):
    resp = client.post(
        "/api/v1/auth/token",
        data={"username": "engineer@example.com", "password": "Engineer123!"},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def db_session():
    """Yield a database session for direct DB manipulation in tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
