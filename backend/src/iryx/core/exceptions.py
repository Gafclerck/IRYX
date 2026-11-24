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


class DatabaseUnavailableException(IryxException):
    """Raised when the database service is unavailable or connection fails."""

    def __init__(
        self,
        message: str = "Service de base de données temporairement indisponible.",
        code: str = "DATABASE_UNAVAILABLE",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


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


class ConflictException(IryxException):
    """Raised when an operation conflicts with the current resource state."""

    def __init__(
        self,
        message: str = "Conflit avec l'état actuel de la ressource.",
        code: str = "CONFLICT",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
        )


class InvalidCredentialsException(UnauthorizedException):
    """Raised when authentication credentials (email or password) are incorrect."""

    def __init__(
        self,
        message: str = "Identifiants invalides.",
        code: str = "INVALID_CREDENTIALS",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class InactiveAccountException(ForbiddenException):
    """Raised when an authenticated user account has been disabled or is inactive."""

    def __init__(
        self,
        message: str = "Compte utilisateur inactif.",
        code: str = "INACTIVE_ACCOUNT",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class InvalidTokenException(UnauthorizedException):
    """Raised when a JWT token is expired, corrupted, or has an invalid signature."""

    def __init__(
        self,
        message: str = "Jeton d'authentification invalide ou expiré.",
        code: str = "INVALID_TOKEN",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class UserNotFoundException(NotFoundException):
    """Raised when a requested user entity is not found."""

    def __init__(
        self,
        message: str = "Utilisateur introuvable.",
        code: str = "USER_NOT_FOUND",
        status_code: int = status.HTTP_404_NOT_FOUND,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )
        self.status_code = status_code


class OrganizationNotFoundException(NotFoundException):
    """Raised when a requested organization does not exist or is inaccessible."""

    def __init__(
        self,
        message: str = "Organisation introuvable.",
        code: str = "ORGANIZATION_NOT_FOUND",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class CaseNotFoundException(NotFoundException):
    """Raised when a requested case entity is not found."""

    def __init__(
        self,
        message: str = "Le dossier demandé n'existe pas.",
        code: str = "CASE_NOT_FOUND",
        status_code: int = status.HTTP_404_NOT_FOUND,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )
        self.status_code = status_code


class InvalidStatusTransitionException(IryxException):
    """Raised when an illegal or unsupported case status transition is attempted."""

    def __init__(
        self,
        message: str = "Transition de statut de dossier non autorisée.",
        code: str = "INVALID_STATUS_TRANSITION",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
        )


class MemberNotFoundException(NotFoundException):
    """Raised when a requested membership does not exist."""

    def __init__(
        self,
        message: str = "Membre introuvable.",
        code: str = "MEMBER_NOT_FOUND",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class MemberAlreadyExistsException(ConflictException):
    """Raised when attempting to add an already registered member to an organization."""

    def __init__(
        self,
        message: str = "Cet utilisateur est déjà membre de l'organisation.",
        code: str = "MEMBER_ALREADY_EXISTS",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class InsufficientPermissionsException(ForbiddenException):
    """Raised when an authenticated user lacks the required RBAC role."""

    def __init__(
        self,
        message: str = "Permissions insuffisantes pour effectuer cette action.",
        code: str = "INSUFFICIENT_PERMISSIONS",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
        )


class CannotRemoveLastAdminException(IryxException):
    """Raised when an operation would leave an organization without an active administrator."""

    def __init__(
        self,
        message: str = "Impossible de supprimer ou rétrograder le dernier administrateur actif.",
        code: str = "CANNOT_REMOVE_LAST_ADMIN",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
        )


class UserAlreadyExistsException(ConflictException):
    """Raised when attempting to create a user with an already registered email."""

    def __init__(
        self,
        message: str = "Un utilisateur avec cette adresse email existe déjà.",
        code: str = "USER_ALREADY_EXISTS",
    ) -> None:
        super().__init__(
            message=message,
            code=code,
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
    headers: dict[str, str] | None = None
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers = {"WWW-Authenticate": "Bearer"}
    return JSONResponse(
        status_code=exc.status_code,
        content=_format_error_response(code=exc.code, message=exc.message),
        headers=headers,
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
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
    }
    code = status_code_map.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "Une erreur HTTP est survenue."

    headers: dict[str, str] | None = getattr(exc, "headers", None)
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers = headers.copy() if headers else {}
        headers.setdefault("WWW-Authenticate", "Bearer")

    return JSONResponse(
        status_code=exc.status_code,
        content=_format_error_response(code=code, message=message),
        headers=headers,
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
