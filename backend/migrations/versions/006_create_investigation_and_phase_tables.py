"""create investigation and phase tables

Revision ID: 006
Revises: 005
Create Date: 2026-11-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create table investigation_runs
    op.create_table(
        "investigation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column(
            "current_phase",
            sa.String(length=64),
            server_default=sa.text("'triage'"),
            nullable=False,
        ),
        sa.Column(
            "validated_plan",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
        sa.Column("iteration_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_investigation_runs_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_runs")),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'paused', 'completed', 'failed')",
            name=op.f("ck_investigation_runs_status_check"),
        ),
        sa.CheckConstraint(
            "iteration_count >= 0",
            name=op.f("ck_investigation_runs_iteration_count_non_negative"),
        ),
        sa.CheckConstraint(
            "error_count >= 0",
            name=op.f("ck_investigation_runs_error_count_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_investigation_runs_case_id"),
        "investigation_runs",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_runs_status"),
        "investigation_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_runs_current_phase"),
        "investigation_runs",
        ["current_phase"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_runs_started_at"),
        "investigation_runs",
        ["started_at"],
        unique=False,
    )

    # 2. Create table phases
    op.create_table(
        "phases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investigation_run_id", sa.Uuid(), nullable=False),
        sa.Column("phase_name", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["investigation_run_id"],
            ["investigation_runs.id"],
            name=op.f("fk_phases_investigation_run_id_investigation_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_phases")),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'completed', 'failed')",
            name=op.f("ck_phases_status_check"),
        ),
    )
    op.create_index(
        op.f("ix_phases_investigation_run_id"),
        "phases",
        ["investigation_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_phases_phase_name"),
        "phases",
        ["phase_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_phases_status"),
        "phases",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_phases_started_at"),
        "phases",
        ["started_at"],
        unique=False,
    )


def downgrade() -> None:
    # 1. Drop table phases
    op.drop_index(op.f("ix_phases_started_at"), table_name="phases")
    op.drop_index(op.f("ix_phases_status"), table_name="phases")
    op.drop_index(op.f("ix_phases_phase_name"), table_name="phases")
    op.drop_index(op.f("ix_phases_investigation_run_id"), table_name="phases")
    op.drop_table("phases")

    # 2. Drop table investigation_runs
    op.drop_index(op.f("ix_investigation_runs_started_at"), table_name="investigation_runs")
    op.drop_index(op.f("ix_investigation_runs_current_phase"), table_name="investigation_runs")
    op.drop_index(op.f("ix_investigation_runs_status"), table_name="investigation_runs")
    op.drop_index(op.f("ix_investigation_runs_case_id"), table_name="investigation_runs")
    op.drop_table("investigation_runs")
