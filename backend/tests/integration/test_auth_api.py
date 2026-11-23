"""Integration tests for Authentication API endpoints (/api/v1/auth/login and /api/v1/auth/me)."""

import uuid
from collections.abc import Generator
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.api.dependencies import get_db
from iryx.auth.models import User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.core.config import get_settings
from iryx.core.security import create_access_token, decode_access_token
from iryx.db.base import Base
from iryx.main import app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for integration testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    # Override the database dependency in FastAPI application
    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def active_user(db_session: Session) -> User:
    """Create and return an active registered test user."""
    user_service = UserService(db_session)
    return user_service.create_user(
        UserCreate(email="analyst@iryx.local", password="SecurePassword123!")
    )


@pytest.fixture
def inactive_user(db_session: Session) -> User:
    """Create and return an inactive test user."""
    user_service = UserService(db_session)
    user = user_service.create_user(
        UserCreate(email="disabled@iryx.local", password="SecurePassword123!")
    )
    user.is_active = False
    db_session.commit()
    db_session.refresh(user)
    return user


def test_login_nominal_success(client: TestClient, active_user: User) -> None:
    """Verify nominal POST /api/v1/auth/login returns HTTP 200 with expires_in=3600."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@iryx.local", "password": "SecurePassword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600

    # Validate decoded JWT claims and cryptographic integrity
    payload = decode_access_token(data["access_token"])
    assert payload["sub"] == str(active_user.id)
    assert payload["email"] == "analyst@iryx.local"
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == 3600


def test_login_email_case_insensitivity(client: TestClient, active_user: User) -> None:
    """Verify login succeeds even when email casing or surrounding whitespace differs."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "  ANALYST@IRYX.LOCAL  ", "password": "SecurePassword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


def test_login_invalid_password_returns_401(client: TestClient, active_user: User) -> None:
    """Verify incorrect password returns HTTP 401 with INVALID_CREDENTIALS error envelope."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "analyst@iryx.local", "password": "WrongPassword999!"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "Identifiants invalides.",
        }
    }


def test_login_unknown_email_returns_401(client: TestClient, active_user: User) -> None:
    """Verify unknown email returns identical HTTP 401 without revealing non-existence."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@iryx.local", "password": "SecurePassword123!"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_CREDENTIALS",
            "message": "Identifiants invalides.",
        }
    }


def test_login_inactive_user_returns_403(client: TestClient, inactive_user: User) -> None:
    """Verify valid credentials for inactive user returns HTTP 403 with INACTIVE_ACCOUNT."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@iryx.local", "password": "SecurePassword123!"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "INACTIVE_ACCOUNT",
            "message": "Compte utilisateur inactif.",
        }
    }


def test_login_validation_errors(client: TestClient) -> None:
    """Verify malformed requests return HTTP 422 with standardized VALIDATION_ERROR envelope."""
    # Malformed email
    r1 = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "ValidPassword123!"},
    )
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Missing password
    r2 = client.post("/api/v1/auth/login", json={"email": "analyst@iryx.local"})
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"

    # Empty payload
    r3 = client.post("/api/v1/auth/login", json={})
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_me_nominal_success(client: TestClient, active_user: User) -> None:
    """Verify GET /api/v1/auth/me returns UserResponse for valid Bearer token."""
    token = create_access_token(data={"sub": str(active_user.id), "email": active_user.email})

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(active_user.id)
    assert data["email"] == active_user.email
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data
    assert "hashed_password" not in data


def test_get_me_missing_authorization_header(client: TestClient) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 401 UNAUTHORIZED when no header is supplied."""
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Authentification requise.",
        }
    }


def test_get_me_malformed_authorization_header(client: TestClient) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 401 UNAUTHORIZED for non-Bearer schemes."""
    # Basic auth scheme
    r1 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert r1.status_code == 401
    assert r1.json()["error"]["code"] == "UNAUTHORIZED"

    # Bearer scheme with empty token
    r2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer "},
    )
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "UNAUTHORIZED"


def test_get_me_expired_token(client: TestClient, active_user: User) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 401 INVALID_TOKEN for expired token."""
    expired_token = create_access_token(
        data={"sub": str(active_user.id), "email": active_user.email},
        expires_delta=timedelta(seconds=-30),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "Jeton d'authentification invalide ou expiré.",
        }
    }


def test_get_me_tampered_signature(client: TestClient, active_user: User) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 401 INVALID_TOKEN for forged signature."""
    valid_token = create_access_token(data={"sub": str(active_user.id), "email": active_user.email})
    tampered_token = valid_token[:-4] + "xxxx"

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "Jeton d'authentification invalide ou expiré.",
        }
    }


def test_get_me_deleted_or_unknown_user(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 401 USER_NOT_FOUND when user ID does not exist."""
    non_existent_id = str(uuid.uuid4())
    token = create_access_token(data={"sub": non_existent_id, "email": "ghost@iryx.local"})

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "USER_NOT_FOUND",
            "message": "Utilisateur introuvable.",
        }
    }


def test_get_me_deactivated_user(client: TestClient, inactive_user: User) -> None:
    """Verify GET /api/v1/auth/me returns HTTP 403 INACTIVE_ACCOUNT for deactivated user."""
    token = create_access_token(data={"sub": str(inactive_user.id), "email": inactive_user.email})

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "INACTIVE_ACCOUNT",
            "message": "Compte utilisateur inactif.",
        }
    }


def test_get_me_missing_sub_claim(client: TestClient) -> None:
    """Verify token missing sub claim is rejected with HTTP 401 INVALID_TOKEN."""
    token = jwt.encode(
        {"email": "no-sub@iryx.local", "exp": 2000000000},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "Jeton d'authentification invalide ou expiré.",
        }
    }
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_get_me_non_uuid_sub_claim(client: TestClient) -> None:
    """Verify token with non-UUID sub claim is rejected with HTTP 401 INVALID_TOKEN."""
    token = jwt.encode(
        {"sub": "not-a-valid-uuid", "email": "invalid-sub@iryx.local", "exp": 2000000000},
        get_settings().jwt_secret_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "Jeton d'authentification invalide ou expiré.",
        }
    }
    assert response.headers.get("WWW-Authenticate") == "Bearer"
