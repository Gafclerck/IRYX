"""Pytest configuration and shared fixtures for IRYX."""

import os
from collections.abc import AsyncGenerator, Callable, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure required environment variables are set for all test runs
os.environ["SECRET_KEY"] = "test-secret-key-for-unit-testing-32-chars-min"
os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"

import iryx.core.security  # noqa: E402
from iryx.api.dependencies import get_db  # noqa: E402
from iryx.core.config import get_settings  # noqa: E402
from iryx.db.base import Base  # noqa: E402
from iryx.main import app  # noqa: E402

# Ultra-fast Argon2 hasher for test suite (1024 KiB memory, 1 iteration, 1 thread)
# Drops password hashing duration from ~190ms down to ~1ms per hash
_fast_hasher = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=1024, parallelism=1),))
if hasattr(iryx.core.security, "_check_needs_rehash"):
    _fast_hasher.needs_rehash = iryx.core.security._check_needs_rehash
iryx.core.security.password_hash = _fast_hasher


@pytest.fixture(scope="session")
def _shared_engine():
    """Session-scoped in-memory SQLite engine with all IRYX tables created once."""
    import iryx.analytics.models  # noqa: F401
    import iryx.audit.models  # noqa: F401
    import iryx.auth.models  # noqa: F401
    import iryx.cases.models  # noqa: F401
    import iryx.evidence.models  # noqa: F401
    import iryx.gateway.models  # noqa: F401
    import iryx.orchestrator.models  # noqa: F401
    import iryx.reporting.models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(_shared_engine) -> Generator[Session, None, None]:
    """Provide an isolated database session with get_db override and table cleanup."""
    TestingSessionLocal = sessionmaker(bind=_shared_engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        session.close()
        # Clean all rows from all tables in reverse dependency order.
        # The append-only ``audit_events`` table cannot be row-deleted (SQL
        # trigger blocks UPDATE/DELETE), so the schema is dropped and recreated.
        with _shared_engine.begin() as conn:
            Base.metadata.drop_all(bind=conn, checkfirst=True)
            Base.metadata.create_all(bind=conn, checkfirst=True)


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear settings cache before each test to guarantee test isolation."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def cleanup_dependency_overrides():
    """Ensure FastAPI dependency overrides are cleanly cleared after each test."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> Callable[[object], dict[str, str]]:
    """Factory fixture generating Authorization header with Bearer JWT for specified user."""

    def _make(user: object) -> dict[str, str]:
        user_id = getattr(user, "id", None)
        email = getattr(user, "email", None)
        token = iryx.core.security.create_access_token(data={"sub": str(user_id), "email": email})
        return {"Authorization": f"Bearer {token}"}

    return _make


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture with disabled exception re-raising for status verification."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def client() -> TestClient:
    """Synchronous Starlette TestClient fixture with disabled server exception re-raising."""
    return TestClient(app, raise_server_exceptions=False)
