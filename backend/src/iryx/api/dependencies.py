"""IRYX Shared FastAPI Dependencies."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from iryx.db.session import get_db_session


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a managed SQLAlchemy session.

    Ensures the session is systematically closed at the end of the request
    lifecycle and handles database unavailability with HTTP 503.
    """
    yield from get_db_session()
