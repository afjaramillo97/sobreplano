"""Indexes on the foreign keys that the read API filters and joins by.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03 10:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision; Postgres does not index foreign keys on its own."""
    op.create_index("ix_projects_developer_id", "projects", ["developer_id"])
    op.create_index("ix_unit_types_project_id", "unit_types", ["project_id"])


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_unit_types_project_id", table_name="unit_types")
    op.drop_index("ix_projects_developer_id", table_name="projects")
