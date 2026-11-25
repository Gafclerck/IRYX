"""IRYX Investigation Run and Phase ORM Models and Enums."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from iryx.db.base import Base

if TYPE_CHECKING:
    from iryx.cases.models import Case


class InvestigationStatus(StrEnum):
    """Lifecycle statuses for an investigation session."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class PhaseName(StrEnum):
    """Names of the investigation phases and nodes."""

    TRIAGE = "triage"
    PLANNER = "planner"
    PLANNING = "planning"
    GATE_H1 = "gate_h1"
    WAITING_H1 = "waiting_h1"
    EXECUTOR = "executor"
    EXECUTION = "execution"
    ANALYST = "analyst"
    ANALYSIS = "analysis"
    VERIFIER = "verifier"
    VERIFICATION = "verification"
    GATE_H2 = "gate_h2"
    WAITING_H2 = "waiting_h2"
    PSEUDONYMIZATION = "pseudonymization"
    GATE_H3 = "gate_h3"
    WAITING_H3 = "waiting_h3"
    REPORTING = "reporting"


class PhaseStatus(StrEnum):
    """Lifecycle statuses for a phase execution."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationRun(Base):
    """Global execution session of an investigation orchestrated by LangGraph."""

    __tablename__ = "investigation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[InvestigationStatus] = mapped_column(
        String(32),
        default=InvestigationStatus.RUNNING,
        server_default=text("'running'"),
        nullable=False,
        index=True,
    )
    current_phase: Mapped[str] = mapped_column(
        String(64),
        default=PhaseName.TRIAGE,
        server_default=text("'triage'"),
        nullable=False,
        index=True,
    )
    validated_plan: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    iteration_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
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
            "status IN ('pending', 'running', 'paused', 'completed', 'failed')",
            name="ck_investigation_runs_status_check",
        ),
        CheckConstraint(
            "iteration_count >= 0",
            name="ck_investigation_runs_iteration_count_non_negative",
        ),
        CheckConstraint(
            "error_count >= 0",
            name="ck_investigation_runs_error_count_non_negative",
        ),
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="investigation_runs",
    )
    phases: Mapped[list["Phase"]] = relationship(
        "Phase",
        back_populates="investigation_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Phase.started_at",
    )

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("status") is None:
            kw["status"] = InvestigationStatus.RUNNING
        if kw.get("current_phase") is None:
            kw["current_phase"] = PhaseName.TRIAGE
        if kw.get("iteration_count") is None:
            kw["iteration_count"] = 0
        if kw.get("error_count") is None:
            kw["error_count"] = 0
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<InvestigationRun id={self.id!r} case_id={self.case_id!r} "
            f"status={self.status!r} current_phase={self.current_phase!r}>"
        )


class Phase(Base):
    """Sub-step of an investigation run tracking active and completed phases."""

    __tablename__ = "phases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[PhaseStatus] = mapped_column(
        String(32),
        default=PhaseStatus.PENDING,
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'completed', 'failed')",
            name="ck_phases_status_check",
        ),
    )

    investigation_run: Mapped["InvestigationRun"] = relationship(
        "InvestigationRun",
        back_populates="phases",
    )

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("status") is None:
            kw["status"] = PhaseStatus.PENDING
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Phase id={self.id!r} investigation_run_id={self.investigation_run_id!r} "
            f"phase_name={self.phase_name!r} status={self.status!r}>"
        )


# Import related models for configure_mappers
import iryx.cases.models  # noqa: F401, E402
