"""IRYX Report ORM model and portable integrity constraints (Story 8.3)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    FunctionElement,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine

from iryx.db.base import Base


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


class Report(Base):
    """Immutable, cryptographically sealed incident report document."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        server_default=text("'draft'"),
        nullable=False,
        index=True,
    )
    generation_id: Mapped[str] = mapped_column(
        String(36),
        default=lambda: str(uuid.uuid4()),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("format IN ('markdown', 'json')", name="format_check"),
        CheckConstraint(
            "status IN ('draft', 'validated', 'exported')",
            name="status_check",
        ),
        CheckConstraint("length(content) > 0", name="content_check"),
        CheckConstraint("version > 0", name="version_check"),
        CheckConstraint(
            LowercaseHex64Check(sha256),
            name="sha256_hex_check",
        ),
        UniqueConstraint("case_id", "version", "format", name="uq_reports_case_version_format"),
        Index("ix_reports_case_id_format", "case_id", "format"),
    )

    def __repr__(self) -> str:
        """Return a safe representation without report content."""
        return (
            f"<Report id={self.id!r} case_id={self.case_id!r} format={self.format!r} "
            f"version={self.version!r} status={self.status!r}>"
        )
