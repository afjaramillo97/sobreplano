"""Scrape runs: add the skipped status to the status CHECK.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Alembic compares CHECK constraints by name only, so a new enum value needs this by hand.
# op.f marks the name as final; otherwise the naming convention would prefix it again.
CONSTRAINT = "ck_scrape_runs_scrape_run_status"


def upgrade() -> None:
    """Apply this revision."""
    op.drop_constraint(op.f(CONSTRAINT), "scrape_runs", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "scrape_runs",
        "status IN ('running', 'succeeded', 'failed', 'skipped')",
    )


def downgrade() -> None:
    """Revert this revision; fails if any skipped run exists."""
    op.drop_constraint(op.f(CONSTRAINT), "scrape_runs", type_="check")
    op.create_check_constraint(
        op.f(CONSTRAINT),
        "scrape_runs",
        "status IN ('running', 'succeeded', 'failed')",
    )
