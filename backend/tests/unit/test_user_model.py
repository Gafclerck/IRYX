"""Unit tests for User ORM model and Pydantic schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from iryx.auth.models import User
from iryx.auth.schemas import UserCreate, UserResponse


def test_user_create_schema_valid() -> None:
    """Verify UserCreate accepts valid email and password >= 12 chars."""
    data = {"email": "analyst@iryx.io", "password": "StrongPassword123!"}
    schema = UserCreate(**data)

    assert schema.email == "analyst@iryx.io"
    assert schema.password == "StrongPassword123!"


def test_user_create_schema_normalizes_email() -> None:
    """Verify UserCreate strips whitespace and lowercases email."""
    schema = UserCreate(email="  ANALYST@Iryx.IO  ", password="StrongPassword123!")
    assert schema.email == "analyst@iryx.io"


def test_user_create_schema_rejects_long_password() -> None:
    """Verify UserCreate rejects password exceeding 128 characters."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="analyst@iryx.io", password="a" * 129)

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("password",) for err in errors)


def test_user_create_schema_rejects_long_email() -> None:
    """Verify UserCreate rejects email exceeding 255 characters."""
    long_email = f"{'a' * 245}@example.com"
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email=long_email, password="StrongPassword123!")

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("email",) for err in errors)


def test_user_create_schema_rejects_short_password() -> None:
    """Verify UserCreate rejects password with fewer than 12 characters."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="analyst@iryx.io", password="short")

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("password",) for err in errors)
    assert any("at least 12 characters" in err["msg"] or "min_length" in str(err) for err in errors)


def test_user_create_schema_rejects_invalid_email() -> None:
    """Verify UserCreate rejects malformed email addresses."""
    with pytest.raises(ValidationError) as exc_info:
        UserCreate(email="not-an-email", password="StrongPassword123!")

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("email",) for err in errors)


def test_user_response_excludes_hashed_password() -> None:
    """Verify UserResponse never contains hashed_password field in schema or serialization."""
    assert "hashed_password" not in UserResponse.model_fields

    now = datetime.now(UTC)
    user_id = uuid.uuid4()

    response = UserResponse(
        id=user_id,
        email="analyst@iryx.io",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    dumped_dict = response.model_dump()
    assert "hashed_password" not in dumped_dict
    assert dumped_dict["id"] == user_id
    assert dumped_dict["email"] == "analyst@iryx.io"

    dumped_json = response.model_dump_json()
    assert "hashed_password" not in dumped_json


def test_user_response_from_orm_model() -> None:
    """Verify UserResponse can be instantiated from User ORM model without leaking hash."""
    now = datetime.now(UTC)
    user_id = uuid.uuid4()

    user_orm = User(
        id=user_id,
        email="forensics@iryx.io",
        hashed_password="$argon2id$v=19$m=65536,t=3,p=4$dummyhash",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    response = UserResponse.model_validate(user_orm)
    assert response.id == user_id
    assert response.email == "forensics@iryx.io"
    assert response.is_active is True
    assert "hashed_password" not in response.model_dump()


def test_user_orm_defaults() -> None:
    """Verify User ORM default properties and UUID generation."""
    user = User(
        email="test@iryx.io",
        hashed_password="$argon2id$v=19$samplehash",
    )

    assert user.is_active is True
    assert isinstance(user.id, uuid.UUID)
    assert user.email == "test@iryx.io"


def test_user_orm_repr() -> None:
    """Verify User __repr__ contains id, email, is_active and omits hashed_password."""
    user = User(
        email="test@iryx.io",
        hashed_password="$argon2id$v=19$samplehash",
    )
    repr_str = repr(user)
    assert "test@iryx.io" in repr_str
    assert "is_active=True" in repr_str
    assert "samplehash" not in repr_str
    assert "hashed_password" not in repr_str
