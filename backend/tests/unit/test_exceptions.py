"""Tests for unified HTTP exception handlers and error response schemas."""

import pytest
from fastapi import APIRouter
from httpx import AsyncClient
from pydantic import BaseModel

from iryx.core.exceptions import (
    EmptyFileException,
    ForbiddenException,
    NotFoundException,
    PayloadTooLargeException,
    UnauthorizedException,
    ValidationException,
)
from iryx.main import app

# Create a dummy router for testing to trigger various exception scenarios
dummy_router = APIRouter(prefix="/_test", tags=["Testing"])


class PayloadModel(BaseModel):
    name: str
    count: int


@dummy_router.get("/unhandled-error")
async def trigger_unhandled_error() -> None:
    """Endpoint intentionally raising an unhandled exception."""
    raise RuntimeError("Unexpected internal crash during database calculation")


@dummy_router.post("/validation-error")
async def trigger_validation_error(payload: PayloadModel) -> dict[str, str]:
    """Endpoint requiring strict payload validation."""
    return {"status": "ok", "name": payload.name}


@dummy_router.get("/not-found-domain")
async def trigger_not_found_domain() -> None:
    """Endpoint raising domain NotFoundException."""
    raise NotFoundException("Dossier introuvable.")


@dummy_router.get("/forbidden-domain")
async def trigger_forbidden_domain() -> None:
    """Endpoint raising domain ForbiddenException."""
    raise ForbiddenException("Accès non autorisé à ce dossier.")


@dummy_router.get("/unauthorized-domain")
async def trigger_unauthorized_domain() -> None:
    """Endpoint raising domain UnauthorizedException."""
    raise UnauthorizedException("Jeton JWT expiré ou invalide.")


@dummy_router.get("/validation-domain")
async def trigger_validation_domain() -> None:
    """Endpoint raising domain ValidationException."""
    raise ValidationException("Le format du hash SHA-256 est invalide.")


@dummy_router.get("/empty-file-domain")
async def trigger_empty_file_domain() -> None:
    """Endpoint raising domain EmptyFileException."""
    raise EmptyFileException()


@dummy_router.get("/payload-too-large-domain")
async def trigger_payload_too_large_domain() -> None:
    """Endpoint raising domain PayloadTooLargeException."""
    raise PayloadTooLargeException()


@dummy_router.get("/http-503-error")
async def trigger_http_503_error() -> None:
    """Endpoint raising generic Starlette HTTPException with 503."""
    from starlette.exceptions import HTTPException as StarletteHTTPException

    raise StarletteHTTPException(
        status_code=503,
        detail="Service tiers temporairement indisponible.",
    )


# Include the test router into app
app.include_router(dummy_router)


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_without_stacktrace(
    async_client: AsyncClient,
) -> None:
    """Verify unhandled exceptions return HTTP 500 without leaking stack traces."""
    response = await async_client.get("/_test/unhandled-error")
    assert response.status_code == 500

    data = response.json()
    assert data == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Une erreur inattendue est survenue.",
        }
    }
    # Verify no traceback or source code paths in response text
    assert "Traceback" not in response.text
    assert "RuntimeError" not in response.text
    assert "Unexpected internal crash" not in response.text


@pytest.mark.asyncio
async def test_request_validation_error_returns_422(
    async_client: AsyncClient,
) -> None:
    """Verify invalid payloads return HTTP 422 with standardized code and message."""
    # Missing required fields
    response = await async_client.post("/_test/validation-error", json={})
    assert response.status_code == 422

    data = response.json()
    assert data == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Données de requête invalides.",
        }
    }
    # Verify no internal Pydantic schema inspection in response
    assert "field required" not in response.text.lower()


@pytest.mark.asyncio
async def test_http_404_not_found_standardized(
    async_client: AsyncClient,
) -> None:
    """Verify requesting non-existent endpoints returns HTTP 404 with standardized error."""
    response = await async_client.get("/non-existent-endpoint-xyz")
    assert response.status_code == 404

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_domain_exceptions_standardized_responses(
    async_client: AsyncClient,
) -> None:
    """Verify domain exceptions map to appropriate HTTP codes and standardized format."""
    # NotFoundException -> 404
    r1 = await async_client.get("/_test/not-found-domain")
    assert r1.status_code == 404
    assert r1.json() == {"error": {"code": "NOT_FOUND", "message": "Dossier introuvable."}}

    # ForbiddenException -> 403
    r2 = await async_client.get("/_test/forbidden-domain")
    assert r2.status_code == 403
    assert r2.json() == {
        "error": {"code": "FORBIDDEN", "message": "Accès non autorisé à ce dossier."}
    }

    # UnauthorizedException -> 401
    r3 = await async_client.get("/_test/unauthorized-domain")
    assert r3.status_code == 401
    assert r3.headers.get("www-authenticate") == "Bearer"
    assert r3.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Jeton JWT expiré ou invalide."}
    }

    # ValidationException -> 422
    r4 = await async_client.get("/_test/validation-domain")
    assert r4.status_code == 422
    assert r4.json() == {
        "error": {"code": "VALIDATION_ERROR", "message": "Le format du hash SHA-256 est invalide."}
    }

    # EmptyFileException -> 400
    r5 = await async_client.get("/_test/empty-file-domain")
    assert r5.status_code == 400
    assert r5.json() == {
        "error": {
            "code": "EMPTY_FILE_ERROR",
            "message": "Le fichier téléversé est vide (0 octet).",
        }
    }

    # PayloadTooLargeException -> 413
    r6 = await async_client.get("/_test/payload-too-large-domain")
    assert r6.status_code == 413
    assert r6.json() == {
        "error": {
            "code": "PAYLOAD_TOO_LARGE",
            "message": "La taille du fichier dépasse la limite autorisée.",
        }
    }


@pytest.mark.asyncio
async def test_http_503_service_unavailable_code_mapping(
    async_client: AsyncClient,
) -> None:
    """Verify generic HTTPException with status 503 maps to SERVICE_UNAVAILABLE."""
    response = await async_client.get("/_test/http-503-error")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "Service tiers temporairement indisponible.",
        }
    }
