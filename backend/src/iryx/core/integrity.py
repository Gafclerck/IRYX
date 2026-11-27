"""Portable integrity helpers shared across report and audit modules (Story 8.5)."""

from typing import Any

from sqlalchemy import Boolean, FunctionElement
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import TypeEngine


class LowercaseHex64Check(FunctionElement[bool]):
    """Portable SQL predicate validating a lowercase SHA-256 hexadecimal string.

    PostgreSQL compiles the predicate as a POSIX regular expression while SQLite
    compiles it as an equivalent 64-character ``GLOB`` pattern. Keeping the two
    representations behind one SQLAlchemy expression prevents ORM metadata and
    Alembic migrations from drifting apart.
    """

    name = "lowercase_hex_64"
    type: TypeEngine[bool] = Boolean()
    inherit_cache = True

    @property
    def column(self) -> Any:
        """Return the checked column expression."""
        return self.clauses.clauses[0]


@compiles(LowercaseHex64Check)
@compiles(LowercaseHex64Check, "postgresql")
def _compile_lowercase_hex_64_postgresql(
    element: LowercaseHex64Check,
    compiler: Any,
    **kw: Any,
) -> str:
    """Compile the predicate with PostgreSQL regex syntax."""
    column = compiler.process(element.column, **kw)
    return f"{column} ~ '^[0-9a-f]{{64}}$'"


@compiles(LowercaseHex64Check, "sqlite")
def _compile_lowercase_hex_64_sqlite(
    element: LowercaseHex64Check,
    compiler: Any,
    **kw: Any,
) -> str:
    """Compile the predicate with SQLite GLOB syntax."""
    column = compiler.process(element.column, **kw)
    pattern = "[0-9a-f]" * 64
    return f"{column} GLOB '{pattern}'"
