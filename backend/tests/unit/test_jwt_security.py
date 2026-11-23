"""Unit tests for JWT creation, decoding, validation, and cryptographic security."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from iryx.core.config import get_settings
from iryx.core.exceptions import InvalidTokenException
from iryx.core.security import create_access_token, decode_access_token


def test_create_access_token_default_expiration() -> None:
    """Verify create_access_token sets iat and exp claims separated by exactly 3600 seconds."""
    user_id = str(uuid.uuid4())
    email = "analyst@iryx.local"

    token = create_access_token(data={"sub": user_id, "email": email})
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["email"] == email
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == 3600


def test_create_access_token_custom_expiration_delta() -> None:
    """Verify create_access_token respects custom expires_delta parameter."""
    user_id = str(uuid.uuid4())
    custom_delta = timedelta(minutes=15)

    token = create_access_token(
        data={"sub": user_id, "email": "test@iryx.local"},
        expires_delta=custom_delta,
    )
    payload = decode_access_token(token)
    assert payload["exp"] - payload["iat"] == 900


def test_decode_access_token_expired_raises_invalid_token_exception() -> None:
    """Verify decode_access_token raises InvalidTokenException (HTTP 401) on expired tokens."""
    user_id = str(uuid.uuid4())
    expired_token = create_access_token(
        data={"sub": user_id, "email": "expired@iryx.local"},
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(InvalidTokenException) as exc_info:
        decode_access_token(expired_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"
    assert "invalide ou expiré" in exc_info.value.message


def test_decode_access_token_tampered_signature() -> None:
    """Verify decode_access_token raises InvalidTokenException when signature is altered."""
    user_id = str(uuid.uuid4())
    valid_token = create_access_token(data={"sub": user_id, "email": "tampered@iryx.local"})

    # Tamper with the last few characters of signature
    parts = valid_token.split(".")
    tampered_sig = ("a" if parts[2][-1] != "a" else "b") + parts[2][:-1]
    tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"

    with pytest.raises(InvalidTokenException) as exc_info:
        decode_access_token(tampered_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"


def test_decode_access_token_wrong_secret_key() -> None:
    """Verify tokens signed with a foreign key cannot be decoded."""
    now = datetime.now(UTC)
    foreign_token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "email": "hacker@iryx.local",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        "foreign-secret-key-not-matching-application",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenException) as exc_info:
        decode_access_token(foreign_token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"


def test_decode_access_token_malformed_string() -> None:
    """Verify decode_access_token raises InvalidTokenException on non-JWT strings."""
    malformed_inputs = [
        "not-a-valid-token",
        "header.payload",
        "",
        "   ",
        "header.payload.signature.extra",
    ]

    for malformed in malformed_inputs:
        with pytest.raises(InvalidTokenException) as exc_info:
            decode_access_token(malformed)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "INVALID_TOKEN"


def test_decode_access_token_algorithm_alignment() -> None:
    """Verify decode_access_token validates against settings.jwt_algorithm."""
    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    decoded = decode_access_token(token)
    assert "sub" in decoded


def test_decode_access_token_missing_required_claims() -> None:
    """Verify decode_access_token raises InvalidTokenException when exp or sub is omitted."""
    settings = get_settings()
    now = datetime.now(UTC)

    # Missing sub claim
    token_no_sub = jwt.encode(
        {"email": "nosub@iryx.local", "exp": int((now + timedelta(hours=1)).timestamp())},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenException) as exc_info:
        decode_access_token(token_no_sub)
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"

    # Missing exp claim
    token_no_exp = jwt.encode(
        {"sub": str(uuid.uuid4()), "email": "noexp@iryx.local"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenException) as exc_info:
        decode_access_token(token_no_exp)
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_TOKEN"


def test_create_access_token_validates_dict_type() -> None:
    """Verify create_access_token raises TypeError when data is not a dict."""
    with pytest.raises(TypeError):
        create_access_token("not-a-dict")  # type: ignore[arg-type]
