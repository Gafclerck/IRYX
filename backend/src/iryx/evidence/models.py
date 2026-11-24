"""IRYX Evidence and IngestionRun ORM Models."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iryx.db.base import Base

if TYPE_CHECKING:
    from iryx.auth.models import User
    from iryx.cases.models import Case


class IngestionStatus(StrEnum):
    """Operational lifecycle statuses for evidence ingestion runs."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Evidence(Base):
    """Evidence entity representing raw digital artifacts imported into an investigation case."""

    __tablename__ = "evidences"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    detected_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "file_size >= 0",
            name="ck_evidences_file_size_non_negative",
        ),
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="evidences",
    )
    importer: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[imported_by],
    )
    ingestion_runs: Mapped[list["IngestionRun"]] = relationship(
        "IngestionRun",
        back_populates="evidence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Evidence id={self.id!r} original_name={self.original_name!r} "
            f"case_id={self.case_id!r} file_size={self.file_size!r}>"
        )


class IngestionRun(Base):
    """Asynchronous ingestion run tracking hash computation, integrity, and pre-analysis."""

    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[IngestionStatus] = mapped_column(
        String(32),
        default=IngestionStatus.PENDING,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_ingestion_runs_status_check",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_ingestion_runs_progress_range",
        ),
    )

    evidence: Mapped["Evidence"] = relationship(
        "Evidence",
        back_populates="ingestion_runs",
    )

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("status") is None:
            kw["status"] = IngestionStatus.PENDING
        if kw.get("progress") is None:
            kw["progress"] = 0
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<IngestionRun id={self.id!r} evidence_id={self.evidence_id!r} "
            f"status={self.status!r} progress={self.progress!r}>"
        )


# Import case models so configure_mappers() resolves Case relationship
import iryx.cases.models  # noqa: F401, E402
