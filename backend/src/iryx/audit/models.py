"""IRYX Audit Event ORM model (schema prepared for Story 8.5)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from iryx.db.base import Base
from iryx.reporting.models import LowercaseHex64Check


class AuditEvent(Base):
    """Append-only audit trail row; no service or trigger lives in Story 8.3."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("length(event_type) > 0", name="event_type_check"),
        CheckConstraint(
            LowercaseHex64Check(payload_sha256),
            name="payload_sha256_hex_check",
        ),
        Index("ix_audit_events_case_id_created_at", "case_id", "created_at"),
    )

    def __repr__(self) -> str:
        """Return a representation that never exposes audit payload content."""
        return (
            f"<AuditEvent id={self.id!r} case_id={self.case_id!r} "
            f"event_type={self.event_type!r} created_at={self.created_at!r}>"
        )
