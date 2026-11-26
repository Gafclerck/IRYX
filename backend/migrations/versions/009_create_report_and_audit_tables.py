"""create reports and audit_events tables

Revision ID: 009
Revises: 008
Create Date: 2026-11-25

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _LowercaseHex64Check(sa.FunctionElement):  # type: ignore[type-arg]
    """Portable lowercase SHA-256 CHECK predicate (mirrors ORM metadata)."""

    name = "lowercase_hex_64"
    type = sa.Boolean()
    inherit_cache = True


@compiles(_LowercaseHex64Check)
@compiles(_LowercaseHex64Check, "postgresql")
def _compile_postgresql(element: Any, compiler: Any, **kw: Any) -> str:
    """Compile the POSIX regular expression used by PostgreSQL."""
    column = compiler.process(element.clauses.clauses[0], **kw)
    return f"{column} ~ '^[0-9a-f]{{64}}$'"


@compiles(_LowercaseHex64Check, "sqlite")
def _compile_sqlite(element: Any, compiler: Any, **kw: Any) -> str:
    """Compile the equivalent 64-character GLOB pattern used by SQLite."""
    column = compiler.process(element.clauses.clauses[0], **kw)
    return f"{column} GLOB '{'[0-9a-f]' * 64}'"


def _uuid_type() -> TypeEngine:
    """Return the generic UUID type matching the ORM metadata on every dialect."""
    return sa.Uuid()


def _json_type() -> TypeEngine:
    """Return JSONB on PostgreSQL and portable JSON elsewhere."""
    try:
        bind = op.get_bind()
        dialect_name = bind.dialect.name if bind is not None else None
    except Exception:
        dialect_name = None
    if dialect_name is None:
        try:
            dialect_name = op.get_context().dialect.name
        except Exception:
            dialect_name = "sqlite"
    return postgresql.JSONB() if dialect_name == "postgresql" else sa.JSON()


def upgrade() -> None:
    """Create reports and audit_events with sealed hashes and append-only FKs."""
    op.create_table(
        "reports",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("case_id", _uuid_type(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("generation_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_reports_case_id_cases"), ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "format IN ('markdown', 'json')", name=op.f("ck_reports_format_check")
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'validated', 'exported')",
            name=op.f("ck_reports_status_check"),
        ),
        sa.CheckConstraint("length(content) > 0", name=op.f("ck_reports_content_check")),
        sa.CheckConstraint("version > 0", name=op.f("ck_reports_version_check")),
        sa.CheckConstraint(
            _LowercaseHex64Check(sa.column("sha256")),
            name=op.f("ck_reports_sha256_hex_check"),
        ),
        sa.UniqueConstraint(
            "case_id", "version", "format", name=op.f("uq_reports_case_version_format")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index(op.f("ix_reports_case_id"), "reports", ["case_id"], unique=False)
    op.create_index(op.f("ix_reports_format"), "reports", ["format"], unique=False)
    op.create_index(op.f("ix_reports_sha256"), "reports", ["sha256"], unique=False)
    op.create_index(op.f("ix_reports_status"), "reports", ["status"], unique=False)
    op.create_index(op.f("ix_reports_generation_id"), "reports", ["generation_id"], unique=False)
    op.create_index(
        op.f("ix_reports_case_id_format"), "reports", ["case_id", "format"], unique=False
    )

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("case_id", _uuid_type(), nullable=False),
        sa.Column("actor_id", _uuid_type(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", _json_type(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_audit_events_actor_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["cases.id"], name=op.f("fk_audit_events_case_id_cases"), ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "length(event_type) > 0", name=op.f("ck_audit_events_event_type_check")
        ),
        sa.CheckConstraint(
            _LowercaseHex64Check(sa.column("payload_sha256")),
            name=op.f("ck_audit_events_payload_sha256_hex_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_case_id"), "audit_events", ["case_id"], unique=False)
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(
        op.f("ix_audit_events_payload_sha256"), "audit_events", ["payload_sha256"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_case_id_created_at"),
        "audit_events",
        ["case_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop both tables and all associated indexes in reverse order."""
    op.drop_index(op.f("ix_audit_events_case_id_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_payload_sha256"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_case_id"), table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index(op.f("ix_reports_case_id_format"), table_name="reports")
    op.drop_index(op.f("ix_reports_generation_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_sha256"), table_name="reports")
    op.drop_index(op.f("ix_reports_format"), table_name="reports")
    op.drop_index(op.f("ix_reports_case_id"), table_name="reports")
    op.drop_table("reports")
