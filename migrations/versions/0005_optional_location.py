"""Projects: allow a NULL location while the developer publishes no map.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-02 20:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
from geoalchemy2 import Geography

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOCATION = Geography(geometry_type="POINT", srid=4326)


def upgrade() -> None:
    """Apply this revision; the GIST index on location is kept as it is."""
    op.alter_column("projects", "location", existing_type=LOCATION, nullable=True)


def downgrade() -> None:
    """Revert this revision; fails if any project has no location."""
    op.alter_column("projects", "location", existing_type=LOCATION, nullable=False)
