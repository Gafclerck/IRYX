"""IRYX Analytics and Observation ORM Models."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
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
    from iryx.evidence.models import Evidence
    from iryx.gateway.models import ToolExecution


class Observation(Base):
    """Observation entity representing normalized technical facts extracted from evidence."""

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidences.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    normalized_content: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    timestamp_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    source_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="observations",
    )
    evidence: Mapped[Optional["Evidence"]] = relationship(
        "Evidence",
        back_populates="observations",
        foreign_keys=[source_id],
    )
    tool_execution: Mapped[Optional["ToolExecution"]] = relationship(
        "ToolExecution",
        back_populates="observations",
        foreign_keys=[tool_execution_id],
    )

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Observation id={self.id!r} case_id={self.case_id!r} "
            f"tool_name={self.tool_name!r} source_location={self.source_location!r}>"
        )


# Import related models for configure_mappers
import iryx.cases.models  # noqa: F401, E402
import iryx.evidence.models  # noqa: F401, E402
import iryx.gateway.models  # noqa: F401, E402
