"""IRYX Authentication Dependencies for FastAPI Routes."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.models import User
from iryx.auth.services import UserService
from iryx.core.exceptions import (
    InactiveAccountException,
    InvalidTokenException,
    UnauthorizedException,
    UserNotFoundException,
)
from iryx.core.security import decode_access_token

# auto_error=False allows us to handle absent headers with our standardized UnauthorizedException
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Validate JWT Bearer token and retrieve the authenticated active user.

    Raises:
        UnauthorizedException (401, UNAUTHORIZED): If Bearer header is missing.
        InvalidTokenException (401, INVALID_TOKEN): If token is expired, invalid or malformed.
        UserNotFoundException (401, USER_NOT_FOUND): If user does not exist in DB.
        InactiveAccountException (403, INACTIVE_ACCOUNT): If user account is deactivated.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedException(
            message="Authentification requise.",
            code="UNAUTHORIZED",
        )

    if credentials.scheme.lower() != "bearer":
        raise UnauthorizedException(
            message="Authentification requise.",
            code="UNAUTHORIZED",
        )

    payload = decode_access_token(credentials.credentials)

    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenException(
            message="Jeton d'authentification invalide ou expiré.",
            code="INVALID_TOKEN",
        )

    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenException(
            message="Jeton d'authentification invalide ou expiré.",
            code="INVALID_TOKEN",
        ) from exc

    user_service = UserService(db)
    user = user_service.get_by_id(user_id)

    if user is None:
        raise UserNotFoundException(
            message="Utilisateur introuvable.",
            code="USER_NOT_FOUND",
            status_code=401,
        )

    if not user.is_active:
        raise InactiveAccountException(
            message="Compte utilisateur inactif.",
            code="INACTIVE_ACCOUNT",
        )

    return user
