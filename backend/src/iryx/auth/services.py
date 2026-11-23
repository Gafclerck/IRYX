"""IRYX User Management and Persistence Services."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from iryx.auth.models import User
from iryx.auth.schemas import UserCreate
from iryx.core.exceptions import (
    InactiveAccountException,
    InvalidCredentialsException,
    UserAlreadyExistsException,
)
from iryx.core.security import hash_password, verify_password

logger = logging.getLogger("iryx.auth.services")


class UserService:
    """Service handling User business logic, persistence, and authentication."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        """Retrieve a user by normalized email address."""
        if not email or not isinstance(email, str):
            return None
        normalized_email = email.lower().strip()
        stmt = select(User).where(User.email == normalized_email)
        return self.db.scalars(stmt).first()

    def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Retrieve a user by its unique identifier."""
        if not user_id:
            return None
        return self.db.get(User, user_id)

    def create_user(self, user_create: UserCreate, auto_commit: bool = True) -> User:
        """Create a new user with hashed password and uniqueness enforcement.

        Raises UserAlreadyExistsException (HTTP 409) if email is already taken.
        """
        normalized_email = user_create.email.lower().strip()

        # Proactive check
        existing_user = self.get_by_email(normalized_email)
        if existing_user is not None:
            raise UserAlreadyExistsException()

        # Hash password strictly with argon2id
        hashed = hash_password(user_create.password)

        new_user = User(
            email=normalized_email,
            hashed_password=hashed,
            is_active=True,
        )

        self.db.add(new_user)
        try:
            if auto_commit:
                self.db.commit()
                self.db.refresh(new_user)
            else:
                self.db.flush()
            return new_user
        except IntegrityError as exc:
            self.db.rollback()
            # Verify if failure is genuinely an email duplicate conflict
            if self.get_by_email(normalized_email) is not None:
                logger.warning(
                    "IntegrityError encountered due to duplicate email=%s",
                    normalized_email,
                    extra={"context": {"email": normalized_email}},
                )
                raise UserAlreadyExistsException() from exc
            logger.warning(
                "IntegrityError encountered during user creation: %s",
                str(exc),
                extra={"context": {"email": normalized_email}},
            )
            raise
        except Exception:
            self.db.rollback()
            raise

    def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate user credentials against argon2id hash and verify active account.

        Raises:
            InvalidCredentialsException (HTTP 401): If user is not found or password fails.
            InactiveAccountException (HTTP 403): If user exists and password matches but inactive.
        """
        if (
            not isinstance(email, str)
            or not email.strip()
            or not isinstance(password, str)
            or not password.strip()
        ):
            raise InvalidCredentialsException()

        normalized_email = email.lower().strip()
        user = self.get_by_email(normalized_email)

        if user is None:
            raise InvalidCredentialsException()

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsException()

        if not user.is_active:
            raise InactiveAccountException()

        return user


def create_user(db: Session, user_create: UserCreate, auto_commit: bool = True) -> User:
    """Helper function to create a new user."""
    return UserService(db).create_user(user_create, auto_commit=auto_commit)


def get_user_by_email(db: Session, email: str) -> User | None:
    """Helper function to fetch a user by email."""
    return UserService(db).get_by_email(email)


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    """Helper function to fetch a user by id."""
    return UserService(db).get_by_id(user_id)


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Helper function to authenticate a user."""
    return UserService(db).authenticate_user(email=email, password=password)
