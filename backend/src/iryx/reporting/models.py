"""IRYX Report ORM model and portable integrity constraints (Story 8.3)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from iryx.core.integrity import LowercaseHex64Check
from iryx.db.base import Base


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
