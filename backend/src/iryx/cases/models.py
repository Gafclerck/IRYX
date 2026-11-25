"""IRYX Investigation Case ORM Models."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iryx.db.base import Base

if TYPE_CHECKING:
    from iryx.analytics.models import Observation
    from iryx.auth.models import Organization, User
    from iryx.evidence.models import Evidence
    from iryx.gateway.models import ToolExecution
    from iryx.orchestrator.models import InvestigationRun


class CaseStatus(StrEnum):
    """Operational lifecycle statuses for investigation cases."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    CLOSED = "closed"


class Case(Base):
    """Case entity representing a digital forensics investigation or fraud analysis."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CaseStatus] = mapped_column(
        String(32),
        default=CaseStatus.OPEN,
        server_default=text("'open'"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'review', 'closed')",
            name="ck_cases_status_check",
        ),
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="cases",
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
    )
    evidences: Mapped[list["Evidence"]] = relationship(
        "Evidence",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tool_executions: Mapped[list["ToolExecution"]] = relationship(
        "ToolExecution",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    investigation_runs: Mapped[list["InvestigationRun"]] = relationship(
        "InvestigationRun",
        back_populates="case",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, **kw) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("status") is None:
            kw["status"] = CaseStatus.OPEN
        super().__init__(**kw)

    def __repr__(self) -> str:
        return f"<Case id={self.id!r} title={self.title!r} status={self.status!r}>"


# Import related models so configure_mappers() resolves relationships
import iryx.analytics.models  # noqa: F401, E402
import iryx.evidence.models  # noqa: F401, E402
import iryx.gateway.models  # noqa: F401, E402
import iryx.orchestrator.models  # noqa: F401, E402
