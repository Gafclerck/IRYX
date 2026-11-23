"""Unit tests for centralized cryptographic security utilities (argon2id)."""

import pytest

from iryx.core.security import hash_password, needs_rehash, verify_password


def test_hash_password_produces_argon2id_format() -> None:
    """Verify hash_password uses argon2id algorithm and prefix."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert hashed.startswith("$argon2id$")
    assert password not in hashed


def test_hash_password_rejects_empty_or_whitespace() -> None:
    """Verify hash_password raises ValueError on empty or whitespace strings."""
    with pytest.raises(ValueError):
        hash_password("")

    with pytest.raises(ValueError):
        hash_password("   ")


def test_needs_rehash() -> None:
    """Verify needs_rehash returns False on fresh hash and True on invalid/outdated."""
    fresh_hash = hash_password("FreshPassword123!")
    assert needs_rehash(fresh_hash) is False
    assert needs_rehash("outdated_or_corrupt_hash") is True


def test_verify_password_nominal_success() -> None:
    """Verify verify_password returns True for matching password and hash."""
    password = "CorrectHorseBatteryStaple123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_failure_on_incorrect_password() -> None:
    """Verify verify_password returns False when given a wrong password."""
    password = "MyValidPassword123!"
    wrong_password = "InvalidPassword123!"
    hashed = hash_password(password)

    assert verify_password(wrong_password, hashed) is False


def test_verify_password_handles_invalid_hash_gracefully() -> None:
    """Verify verify_password returns False without raising exceptions on corrupted hashes."""
    password = "ValidPassword123!"

    # Corrupted / malformed hash strings
    assert verify_password(password, "not_a_hash") is False
    assert verify_password(password, "") is False
    assert verify_password(password, "$argon2id$invalid_payload") is False
    assert verify_password(password, "$2b$12$invalidsaltandhashstring") is False


def test_argon2id_generates_unique_salts() -> None:
    """Verify multiple hashes of identical plaintext generate distinct salted hashes."""
    password = "RepeatablePassword123!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    assert hash1 != hash2
    assert hash1.startswith("$argon2id$")
    assert hash2.startswith("$argon2id$")
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True
