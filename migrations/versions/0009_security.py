"""Security: rate limit counters, and no table access for the Supabase API roles.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_ROLES = "anon, authenticated"


def upgrade() -> None:
    """Apply this revision.

    The API connects as the table owner, so revoking from anon and authenticated changes
    nothing for it. RLS without policies already denied them rows; with no grant either, a
    policy written wrongly later still opens nothing.
    """
    op.create_table(
        "rate_limit_hits",
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("window_kind", sa.Text(), nullable=False),
        sa.Column("client_key", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "window_kind IN ('minute', 'day')", name=op.f("ck_rate_limit_hits_window_kind_known")
        ),
        sa.CheckConstraint("hits > 0", name=op.f("ck_rate_limit_hits_hits_positive")),
        sa.PrimaryKeyConstraint(
            "bucket", "window_kind", "client_key", "window_start", name=op.f("pk_rate_limit_hits")
        ),
    )
    # Same rule as 0001 and 0002: RLS on with no policies.
    op.execute("ALTER TABLE rate_limit_hits ENABLE ROW LEVEL SECURITY")

    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {API_ROLES}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {API_ROLES}")
    # Tables and sequences created from now on by this role start without those grants.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {API_ROLES}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {API_ROLES}"
    )


def downgrade() -> None:
    """Revert this revision.

    Drops the counters. The REVOKEs are not undone: giving anon and authenticated access
    to the tables again would open the database to the Supabase API, so it stays closed.
    """
    op.drop_table("rate_limit_hits")
