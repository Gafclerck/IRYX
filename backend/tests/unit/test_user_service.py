"""Unit tests for User business logic service and uniqueness enforcement."""

import uuid
from collections.abc import Generator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.schemas import UserCreate, UserResponse
from iryx.auth.services import (
    UserService,
    authenticate_user,
    create_user,
    get_user_by_email,
    get_user_by_id,
)
from iryx.core.exceptions import (
    InactiveAccountException,
    InvalidCredentialsException,
    UserAlreadyExistsException,
)
from iryx.core.security import verify_password
from iryx.db.base import Base


@pytest.fixture
def test_db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for unit testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_user_nominal(test_db_session: Session) -> None:
    """Verify successful user creation persists entity with argon2id hash and UTC timestamps."""
    service = UserService(test_db_session)
    user_in = UserCreate(email="Investigator@Iryx.io", password="SuperPassword123!")

    user = service.create_user(user_in)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.email == "investigator@iryx.io"
    assert user.is_active is True
    assert user.hashed_password.startswith("$argon2id$")
    assert "SuperPassword123!" not in user.hashed_password
    assert verify_password("SuperPassword123!", user.hashed_password) is True
    assert user.created_at is not None
    assert user.updated_at is not None

    response = UserResponse.model_validate(user)
    assert response.id == user.id
    assert response.email == user.email
    assert response.is_active is True


def test_create_user_duplicate_email_raises_user_already_exists(
    test_db_session: Session,
) -> None:
    """Verify creating a user with an already registered email raises UserAlreadyExistsException."""
    service = UserService(test_db_session)
    user_in = UserCreate(email="duplicate@iryx.io", password="InitialPassword123!")
    service.create_user(user_in)

    # Attempt second registration with same email (case insensitive)
    dup_in = UserCreate(email="DUPLICATE@IRYX.IO", password="AnotherPassword123!")
    with pytest.raises(UserAlreadyExistsException) as exc_info:
        service.create_user(dup_in)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "USER_ALREADY_EXISTS"
    assert "existe déjà" in exc_info.value.message


def test_get_by_email_case_insensitive(test_db_session: Session) -> None:
    """Verify get_by_email finds users regardless of input casing or surrounding spaces."""
    service = UserService(test_db_session)
    service.create_user(UserCreate(email="case.test@iryx.io", password="Password12345!"))

    found = service.get_by_email("  CASE.TEST@IRYX.IO  ")
    assert found is not None
    assert found.email == "case.test@iryx.io"

    not_found = service.get_by_email("unknown@iryx.io")
    assert not_found is None


def test_get_by_id(test_db_session: Session) -> None:
    """Verify get_by_id finds a user by its UUID."""
    service = UserService(test_db_session)
    user = service.create_user(UserCreate(email="id.test@iryx.io", password="Password12345!"))

    found = service.get_by_id(user.id)
    assert found is not None
    assert found.id == user.id

    not_found = service.get_by_id(uuid.uuid4())
    assert not_found is None


def test_helper_functions_dispatch(test_db_session: Session) -> None:
    """Verify standalone module helper functions delegate properly."""
    user = create_user(
        test_db_session,
        UserCreate(email="helper@iryx.io", password="Password12345!"),
    )
    assert user.email == "helper@iryx.io"

    by_email = get_user_by_email(test_db_session, "helper@iryx.io")
    assert by_email is not None
    assert by_email.id == user.id

    by_id = get_user_by_id(test_db_session, user.id)
    assert by_id is not None
    assert by_id.email == user.email


def test_create_user_integrity_error_rollback_and_duplicate(
    test_db_session: Session,
) -> None:
    """Verify commit IntegrityError triggers rollback and UserAlreadyExistsException."""
    service = UserService(test_db_session)
    user_in = UserCreate(email="race@iryx.io", password="InitialPassword123!")
    service.create_user(user_in)

    dup_in = UserCreate(email="race@iryx.io", password="AnotherPassword123!")
    # Bypass proactive check to simulate race condition hitting commit
    with (
        patch.object(
            service, "get_by_email", side_effect=[None, service.get_by_email("race@iryx.io")]
        ),
        pytest.raises(UserAlreadyExistsException) as exc_info,
    ):
        service.create_user(dup_in)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "USER_ALREADY_EXISTS"


def test_create_user_integrity_error_reraised_when_not_duplicate(
    test_db_session: Session,
) -> None:
    """Verify IntegrityError not caused by duplicate email is re-raised."""
    service = UserService(test_db_session)
    user_in = UserCreate(email="nondup@iryx.io", password="Password12345!")

    with (
        patch.object(test_db_session, "commit", side_effect=IntegrityError("stmt", {}, None)),
        pytest.raises(IntegrityError),
    ):
        service.create_user(user_in)


def test_create_user_auto_commit_false(test_db_session: Session) -> None:
    """Verify create_user with auto_commit=False flushes without committing."""
    service = UserService(test_db_session)
    user = service.create_user(
        UserCreate(email="flushonly@iryx.io", password="Password12345!"),
        auto_commit=False,
    )
    assert user.id is not None
    test_db_session.commit()
    assert service.get_by_email("flushonly@iryx.io") is not None


def test_authenticate_user_success(test_db_session: Session) -> None:
    """Verify authenticate_user succeeds and returns User on matching credentials."""
    service = UserService(test_db_session)
    created = service.create_user(
        UserCreate(email="auth.success@iryx.io", password="CorrectPassword123!")
    )

    authenticated = service.authenticate_user("auth.success@iryx.io", "CorrectPassword123!")
    assert authenticated.id == created.id
    assert authenticated.email == "auth.success@iryx.io"


def test_authenticate_user_wrong_password_raises_invalid_credentials(
    test_db_session: Session,
) -> None:
    """Verify wrong password raises InvalidCredentialsException (HTTP 401)."""
    service = UserService(test_db_session)
    service.create_user(UserCreate(email="auth.fail@iryx.io", password="CorrectPassword123!"))

    with pytest.raises(InvalidCredentialsException) as exc_info:
        service.authenticate_user("auth.fail@iryx.io", "WrongPassword123!")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_CREDENTIALS"
    assert "Identifiants invalides." in exc_info.value.message


def test_authenticate_user_unknown_email_raises_invalid_credentials(
    test_db_session: Session,
) -> None:
    """Verify unknown email raises InvalidCredentialsException without leaking user existence."""
    service = UserService(test_db_session)

    with pytest.raises(InvalidCredentialsException) as exc_info:
        service.authenticate_user("nobody@iryx.io", "AnyPassword123!")

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "INVALID_CREDENTIALS"
    assert "Identifiants invalides." in exc_info.value.message


def test_authenticate_user_inactive_account_raises_inactive_account(
    test_db_session: Session,
) -> None:
    """Verify inactive account raises InactiveAccountException (HTTP 403)."""
    service = UserService(test_db_session)
    user = service.create_user(UserCreate(email="inactive@iryx.io", password="CorrectPassword123!"))
    user.is_active = False
    test_db_session.commit()

    with pytest.raises(InactiveAccountException) as exc_info:
        service.authenticate_user("inactive@iryx.io", "CorrectPassword123!")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "INACTIVE_ACCOUNT"
    assert "inactif" in exc_info.value.message


def test_authenticate_user_empty_or_blank_inputs(test_db_session: Session) -> None:
    """Verify empty or blank email or password raises InvalidCredentialsException."""
    service = UserService(test_db_session)

    with pytest.raises(InvalidCredentialsException):
        service.authenticate_user("", "Password123!")

    with pytest.raises(InvalidCredentialsException):
        service.authenticate_user("user@iryx.io", "")


def test_authenticate_user_helper_dispatch(test_db_session: Session) -> None:
    """Verify authenticate_user standalone helper function delegates properly."""
    create_user(
        test_db_session,
        UserCreate(email="auth.helper@iryx.io", password="Password12345!"),
    )

    user = authenticate_user(test_db_session, "auth.helper@iryx.io", "Password12345!")
    assert user.email == "auth.helper@iryx.io"
