"""IRYX Centralized Cryptographic Security Utilities."""

import logging

from pwdlib import PasswordHash

logger = logging.getLogger("iryx.security")

# Initialize PasswordHash using argon2id recommended configuration
password_hash = PasswordHash.recommended()


def _check_needs_rehash(hash_val: str | bytes) -> bool:
    """Fallback check for needs_rehash across registered hashers."""
    try:
        for hasher in password_hash.hashers:
            if hasher.identify(hash_val):
                return bool(
                    hasher != password_hash.current_hasher
                    or hasher.check_needs_rehash(hash_val)
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
