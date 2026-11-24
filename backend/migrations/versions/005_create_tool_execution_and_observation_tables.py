"""create tool execution and observation tables

Revision ID: 005
Revises: 004
Create Date: 2026-11-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create table tool_executions
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_version", sa.String(length=64), nullable=False),
        sa.Column("agent_role", sa.String(length=64), nullable=False),
        sa.Column(
            "parameters",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("result_sha256", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'success'"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_tool_executions_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_executions")),
        sa.CheckConstraint(
            "status IN ('success', 'error', 'timeout')",
            name=op.f("ck_tool_executions_status_check"),
        ),
        sa.CheckConstraint(
            "duration_ms >= 0",
            name=op.f("ck_tool_executions_duration_ms_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_tool_executions_case_id"),
        "tool_executions",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_executions_tool_name"),
        "tool_executions",
        ["tool_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_executions_status"),
        "tool_executions",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tool_executions_created_at"),
        "tool_executions",
        ["created_at"],
        unique=False,
    )

    # 2. Create table observations
    op.create_table(
        "observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_execution_id", sa.Uuid(), nullable=True),
        sa.Column(
            "normalized_content",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_location", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_observations_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["evidences.id"],
            name=op.f("fk_observations_source_id_evidences"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_execution_id"],
            ["tool_executions.id"],
            name=op.f("fk_observations_tool_execution_id_tool_executions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observations")),
    )
    op.create_index(
        op.f("ix_observations_case_id"),
        "observations",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observations_source_id"),
        "observations",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observations_tool_execution_id"),
        "observations",
        ["tool_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observations_tool_name"),
        "observations",
        ["tool_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observations_timestamp_utc"),
        "observations",
        ["timestamp_utc"],
        unique=False,
    )
    op.create_index(
        op.f("ix_observations_created_at"),
        "observations",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # 1. Drop observations table and indexes
    op.drop_index(op.f("ix_observations_created_at"), table_name="observations")
    op.drop_index(op.f("ix_observations_timestamp_utc"), table_name="observations")
    op.drop_index(op.f("ix_observations_tool_name"), table_name="observations")
    op.drop_index(op.f("ix_observations_tool_execution_id"), table_name="observations")
    op.drop_index(op.f("ix_observations_source_id"), table_name="observations")
    op.drop_index(op.f("ix_observations_case_id"), table_name="observations")
    op.drop_table("observations")

    # 2. Drop tool_executions table and indexes
    op.drop_index(op.f("ix_tool_executions_created_at"), table_name="tool_executions")
    op.drop_index(op.f("ix_tool_executions_status"), table_name="tool_executions")
    op.drop_index(op.f("ix_tool_executions_tool_name"), table_name="tool_executions")
    op.drop_index(op.f("ix_tool_executions_case_id"), table_name="tool_executions")
    op.drop_table("tool_executions")
