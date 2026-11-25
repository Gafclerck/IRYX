"""create observations case_id timestamp_utc index

Revision ID: 008
Revises: 007
Create Date: 2026-11-25

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create composite index on observations (case_id, timestamp_utc) for NFR-PERF-07
    op.create_index(
        op.f("ix_observations_case_id_timestamp_utc"),
        "observations",
        ["case_id", "timestamp_utc"],
        unique=False,
    )


def downgrade() -> None:
    # Drop composite index on observations
    op.drop_index(
        op.f("ix_observations_case_id_timestamp_utc"),
        table_name="observations",
    )
