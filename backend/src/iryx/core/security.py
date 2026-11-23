"""IRYX Centralized Cryptographic Security Utilities."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from iryx.core.config import get_settings
from iryx.core.exceptions import InvalidTokenException

logger = logging.getLogger("iryx.security")

# Initialize PasswordHash using argon2id recommended configuration
password_hash = PasswordHash.recommended()


def _check_needs_rehash(hash_val: str | bytes) -> bool:
    """Fallback check for needs_rehash across registered hashers."""
    try:
        for hasher in password_hash.hashers:
            if hasher.identify(hash_val):
                return bool(
                    hasher != password_hash.current_hasher or hasher.check_needs_rehash(hash_val)
                )
        return True
    except Exception:
        return True


if not hasattr(password_hash, "needs_rehash"):
    password_hash.needs_rehash = _check_needs_rehash


def hash_password(password: str) -> str:
    """Hash a plaintext password using argon2id.

    Returns the hashed password string starting with '$argon2id$'.
    Raises ValueError if password is empty or not a string.
    """
    if not password or not isinstance(password, str) or not password.strip():
        raise ValueError("Password must be a non-empty string.")
    hashed = password_hash.hash(password)
    if not hashed.startswith("$argon2id$"):
        raise ValueError("Password hash does not conform to argon2id format.")
    return hashed


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an argon2id hash.

    Returns True if valid, False otherwise without raising exceptions.
    """
    try:
        return bool(password_hash.verify(plain_password, hashed_password))
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if the given hashed password needs to be rehashed.

    Returns True if the hash algorithm or parameters are outdated, False otherwise.
    """
    try:
        return bool(password_hash.needs_rehash(hashed_password))
    except Exception:
        return True


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token.

    Encodes payload with subject, email, iat and exp claims.
    Uses configurable algorithm (HS256) and jwt_secret_key via Settings.
    """
    if not isinstance(data, dict):
        raise TypeError("data must be a dictionary.")

    settings = get_settings()
    to_encode = data.copy()
    now = datetime.now(UTC)

    if "iat" not in to_encode:
        to_encode["iat"] = int(now.timestamp())
    elif isinstance(to_encode["iat"], datetime):
        to_encode["iat"] = int(to_encode["iat"].timestamp())

    if expires_delta is not None:
        expire_dt = now + expires_delta
        to_encode["exp"] = int(expire_dt.timestamp())
    elif "exp" not in to_encode:
        expire_dt = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        to_encode["exp"] = int(expire_dt.timestamp())
    elif isinstance(to_encode["exp"], datetime):
        to_encode["exp"] = int(to_encode["exp"].timestamp())

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Verifies the cryptographic signature and token expiration.
    Raises InvalidTokenException if the token is expired, corrupted,
    or has an invalid signature.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise InvalidTokenException(
            message="Jeton d'authentification invalide ou expiré.",
            code="INVALID_TOKEN",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            token.strip(),
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        logger.warning("JWT token signature has expired: %s", str(exc))
        raise InvalidTokenException(
            message="Jeton d'authentification invalide ou expiré.",
            code="INVALID_TOKEN",
        ) from exc
    except jwt.PyJWTError as exc:
        logger.warning("JWT token decoding failed: %s", str(exc))
        raise InvalidTokenException(
            message="Jeton d'authentification invalide ou expiré.",
            code="INVALID_TOKEN",
        ) from exc
