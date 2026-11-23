"""Tests for SQLAlchemy session lifecycle, FastAPI get_db dependency, and 503 error handling."""

import logging
from collections.abc import AsyncGenerator
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.core.exceptions import DatabaseUnavailableException, NotFoundException
from iryx.db import mask_database_url, sanitize_error_message
from iryx.db.session import get_db_session
from iryx.main import create_app

# Create an isolated test router with endpoints testing session dependency behavior
db_test_router = APIRouter(prefix="/_test_db", tags=["DB Testing"])


@db_test_router.get("/session-nominal")
def nominal_endpoint(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Test endpoint verifying active session injection."""
    assert isinstance(db, Session)
    return {"status": "ok", "session_type": type(db).__name__}


@db_test_router.get("/db-error-operational")
def operational_error_endpoint(db: Annotated[Session, Depends(get_db)]) -> None:
    """Test endpoint simulating database operational crash / unavailable."""
    raise OperationalError(
        statement="SELECT 1",
        params={},
        orig=Exception(
            "connection refused to postgresql+psycopg://iryx:iryx_password@localhost:5432/iryx_db"
        ),
    )


@db_test_router.get("/db-error-integrity")
def integrity_error_endpoint(db: Annotated[Session, Depends(get_db)]) -> None:
    """Test endpoint raising IntegrityError to ensure constraint violation is not mapped to 503."""
    raise IntegrityError(
        statement="INSERT INTO test",
        params={},
        orig=Exception("duplicate key value violates unique constraint"),
    )


@db_test_router.get("/domain-error-passthrough")
def domain_error_endpoint(db: Annotated[Session, Depends(get_db)]) -> None:
    """Test endpoint verifying non-db exceptions are not masked as 503."""
    raise NotFoundException("Dossier introuvable.")


@pytest.fixture
def db_test_app() -> FastAPI:
    """Isolated FastAPI application for database dependency tests, avoiding global app pollution."""
    test_application = create_app()
    test_application.include_router(db_test_router)
    return test_application


@pytest.fixture
async def db_async_client(db_test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound strictly to the isolated test application."""
    transport = ASGITransport(app=db_test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def test_mask_database_url_hides_sensitive_credentials():
    """Verify mask_database_url properly obfuscates passwords."""
    raw_url = "postgresql+psycopg://iryx:super_secret_password_123@localhost:5432/iryx_db"
    masked = mask_database_url(raw_url)
    assert "super_secret_password_123" not in masked
    assert "***" in masked
    assert "postgresql+psycopg://iryx:***@localhost:5432/iryx_db" in masked


def test_mask_database_url_fallback_on_unparseable_target():
    """Verify mask_database_url fallback on unparseable target or URL without username."""
    # Target without username
    no_user_url = "postgresql://:secret123@localhost:5432/test"
    masked_no_user = mask_database_url(no_user_url)
    assert "secret123" not in masked_no_user
    assert "***" in masked_no_user

    # Completely unparseable target
    invalid_url = "not_a_valid_url://invalid password=mysecret"
    masked_invalid = mask_database_url(invalid_url)
    assert "mysecret" not in masked_invalid
    assert "password=***" in masked_invalid


def test_sanitize_error_message():
    """Verify sanitize_error_message strips credentials from connection error strings."""
    msg1 = "Connection failed to postgresql+psycopg://admin:mysecret123@db:5432/iryx"
    cleaned1 = sanitize_error_message(msg1)
    assert "mysecret123" not in cleaned1
    assert "postgresql+psycopg://admin:***@db:5432/iryx" in cleaned1

    msg2 = "FATAL: password authentication failed for user iryx password=cleartextpwd"
    cleaned2 = sanitize_error_message(msg2)
    assert "cleartextpwd" not in cleaned2
    assert "password=***" in cleaned2

    # Quoted single and double quotes
    msg3 = "Auth failure password='single_quoted_secret' and pwd=\"double_quoted_secret\""
    cleaned3 = sanitize_error_message(msg3)
    assert "single_quoted_secret" not in cleaned3
    assert "double_quoted_secret" not in cleaned3
    assert "password=***" in cleaned3


def test_session_lifecycle_guaranteed_closure():
    """Verify session generator yields a valid session and closes it in finally block."""
    mock_session = MagicMock(spec=Session)

    with patch("iryx.db.session.SessionLocal", return_value=mock_session):
        gen = get_db_session()
        session = next(gen)
        assert session is mock_session
        assert mock_session.close.call_count == 0

        # End generator lifecycle
        with pytest.raises(StopIteration):
            next(gen)

        assert mock_session.close.call_count == 1


def test_session_rollback_and_critical_log_on_database_error(caplog: pytest.LogCaptureFixture):
    """Verify DB errors trigger rollback, CRITICAL logging with masked URL, and raise 503."""
    mock_session = MagicMock(spec=Session)
    raw_db_password = "very_secret_db_password"
    secret_url = f"postgresql+psycopg://iryx:{raw_db_password}@localhost:5432/iryx_db"

    with (
        patch("iryx.db.session.SessionLocal", return_value=mock_session),
        patch("iryx.db.session.engine.url") as mock_url,
    ):
        mock_url.render_as_string.return_value = (
            "postgresql+psycopg://iryx:***@localhost:5432/iryx_db"
        )

        with caplog.at_level(logging.CRITICAL, logger="iryx.db"):
            gen = get_db_session()
            _ = next(gen)

            with pytest.raises(DatabaseUnavailableException) as exc_info:
                gen.throw(
                    OperationalError(
                        statement="SELECT 1",
                        params={},
                        orig=Exception(f"Connection failed: {secret_url}"),
                    )
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.code == "DATABASE_UNAVAILABLE"
            assert mock_session.rollback.call_count == 1
            assert mock_session.close.call_count == 1

        # Check logs
        assert any(record.levelno == logging.CRITICAL for record in caplog.records)
        # Raw password must NEVER appear in logs
        for record in caplog.records:
            assert raw_db_password not in record.message
            assert raw_db_password not in str(record.__dict__)


def test_session_rollback_error_guarded_on_broken_socket():
    """Verify that if session.rollback() fails on a broken socket, 503 is still raised."""
    mock_session = MagicMock(spec=Session)
    mock_session.rollback.side_effect = OperationalError(
        statement="ROLLBACK", params={}, orig=Exception("socket broken")
    )

    with patch("iryx.db.session.SessionLocal", return_value=mock_session):
        gen = get_db_session()
        _ = next(gen)

        with pytest.raises(DatabaseUnavailableException):
            gen.throw(
                InterfaceError(
                    statement="SELECT 1", params={}, orig=Exception("connection disconnected")
                )
            )

        assert mock_session.close.call_count == 1


@pytest.mark.asyncio
async def test_fastapi_injection_nominal(db_async_client: AsyncClient):
    """Verify FastAPI route successfully injects session through get_db."""
    mock_session = MagicMock(spec=Session)

    with patch("iryx.db.session.SessionLocal", return_value=mock_session):
        response = await db_async_client.get("/_test_db/session-nominal")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "session_type": "MagicMock"}
        assert mock_session.close.call_count == 1


@pytest.mark.asyncio
async def test_fastapi_database_unavailable_returns_503_without_leak(
    db_async_client: AsyncClient, caplog: pytest.LogCaptureFixture
):
    """Verify DB failure returns HTTP 503 with standardized error format and no password leak."""
    raw_password = "iryx_password"

    with caplog.at_level(logging.CRITICAL, logger="iryx.db"):
        response = await db_async_client.get("/_test_db/db-error-operational")
        assert response.status_code == 503
        data = response.json()
        assert data == {
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "Service de base de données temporairement indisponible.",
            }
        }
        # Verify no password leak in HTTP response
        assert raw_password not in response.text
        assert "OperationalError" not in response.text

    # Verify no password in captured logs
    for record in caplog.records:
        assert raw_password not in record.message


@pytest.mark.asyncio
async def test_fastapi_integrity_error_not_converted_to_503(db_async_client: AsyncClient):
    """Verify IntegrityError constraint violations are not converted to 503."""
    response = await db_async_client.get("/_test_db/db-error-integrity")
    # IntegrityError is not in DB_EXCEPTIONS, so it bubbles to unhandled_exception_handler (500)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


@pytest.mark.asyncio
async def test_fastapi_non_db_exceptions_not_converted_to_503(db_async_client: AsyncClient):
    """Verify non-database exceptions pass through untouched and return 404."""
    response = await db_async_client.get("/_test_db/domain-error-passthrough")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "NOT_FOUND", "message": "Dossier introuvable."}}
