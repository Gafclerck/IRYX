"""IRYX Unified Exception Hierarchy and HTTP Error Handlers."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("iryx.exceptions")


# Use modern Starlette RFC 9110 status codes to avoid deprecation warnings
HTTP_422_STATUS = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
HTTP_413_STATUS = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)


class IryxException(Exception):
    """Base exception for all IRYX business domain and operational exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class ValidationException(IryxException):
    """Raised when incoming data or entity invariants fail validation."""

    def __init__(
        self,
        message: str = "Données de requête invalides.",
        code: str = "VALIDATION_ERROR",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=HTTP_422_STATUS,
        )


class NotFoundException(IryxException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str = "Ressource introuvable.",
        code: str = "NOT_FOUND",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ForbiddenException(IryxException):
    """Raised when an authenticated entity lacks permission to access a resource."""

    def __init__(
        self,
        message: str = "Accès refusé à cette ressource.",
        code: str = "FORBIDDEN",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class UnauthorizedException(IryxException):
    """Raised when authentication credentials are missing or invalid."""

    def __init__(
        self,
        message: str = "Authentification requise.",
        code: str = "UNAUTHORIZED",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


def _format_error_response(code: str, message: str) -> dict[str, Any]:
    """Return the standardized error response envelope."""
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


async def iryx_exception_handler(request: Request, exc: IryxException) -> JSONResponse:
    """Handle custom IryxException instances."""
    return JSONResponse(
        status_code=exc.status_code,
        content=_format_error_response(code=exc.code, message=exc.message),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle FastAPI / Pydantic RequestValidationError (HTTP 422).

    Returns a standardized error response without leaking stack traces or internal schemas.
    """
    return JSONResponse(
        status_code=HTTP_422_STATUS,
        content=_format_error_response(
            code="VALIDATION_ERROR",
            message="Données de requête invalides.",
        ),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle Starlette / FastAPI HTTPException instances."""
    status_code_map = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_409_CONFLICT: "CONFLICT",
        HTTP_413_STATUS: "PAYLOAD_TOO_LARGE",
        HTTP_422_STATUS: "VALIDATION_ERROR",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
    }
    code = status_code_map.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "Une erreur HTTP est survenue."

    return JSONResponse(
        status_code=exc.status_code,
        content=_format_error_response(code=code, message=message),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors (HTTP 500).

    Logs the error with stack trace internally while returning a sanitized response to the client.
    """
    logger.error(
        "Unexpected server error processing request: %s",
        str(exc),
        exc_info=exc,
        extra={
            "context": {
                "method": request.method,
                "path": request.url.path,
            }
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_format_error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Une erreur inattendue est survenue.",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all unified exception handlers on the FastAPI application."""
    app.add_exception_handler(IryxException, iryx_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
