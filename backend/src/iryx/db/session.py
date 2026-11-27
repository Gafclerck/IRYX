"""IRYX SQLAlchemy Engine, Session Configuration, and Session Generator."""

import contextlib
import logging
import re
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from iryx.core.config import get_settings
from iryx.core.exceptions import DatabaseUnavailableException

logger = logging.getLogger("iryx.db")

db_exceptions: list[type[Exception]] = [OperationalError, InterfaceError]
try:
    import psycopg

    db_exceptions.append(psycopg.OperationalError)
except ImportError:
    pass

DB_EXCEPTIONS: tuple[type[Exception], ...] = tuple(db_exceptions)

settings = get_settings()

engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def sanitize_error_message(msg: str) -> str:
    """Mask any connection strings or passwords embedded inside error messages."""
    # Mask URL passwords with or without username: scheme://[user]:pass@host
    sanitized = re.sub(r"://([^:]*):([^@]+)@", r"://\1:***@", msg)
    # Mask key-value password parameters including quoted variants
    sanitized = re.sub(
        r"(?:password|pwd)=(?:'[^']*'|\"[^\"]*\"|[^\s,;'\"&]+)",
        "password=***",
        sanitized,
        flags=re.I,
    )
    return sanitized


def mask_database_url(target: str | Engine) -> str:
    """Mask credentials and passwords in a database URL string or Engine."""
    if isinstance(target, Engine):
        try:
            rendered = target.url.render_as_string(hide_password=True)
        except Exception:
            rendered = str(target.url)
        return sanitize_error_message(rendered)
    try:
        rendered = make_url(target).render_as_string(hide_password=True)
    except Exception:
        # Fallback for unparseable targets or custom formats
        rendered = str(target)
    return sanitize_error_message(rendered)


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session with guaranteed closure and error handling.

    Catches database connection or operational exceptions, logs at CRITICAL level
    with masked credentials, rolls back uncommitted transactions, and raises
    DatabaseUnavailableException (HTTP 503).
    """
    session: Session | None = None
    try:
        session = SessionLocal()
        yield session
    except DB_EXCEPTIONS as exc:
        masked_url = mask_database_url(engine)
        sanitized_error = sanitize_error_message(str(exc))
        logger.critical(
            "Database error encountered for engine URL: %s. Error: %s",
            masked_url,
            sanitized_error,
            extra={"context": {"db_url": masked_url}},
        )
        raise DatabaseUnavailableException() from exc
    finally:
        if session is not None:
            # Guarantee rollback of any uncommitted work on every exit path so a
            # failure inside (e.g. an audit insertion) can never leak a partial write.
            with contextlib.suppress(Exception):
                session.rollback()
            session.close()
