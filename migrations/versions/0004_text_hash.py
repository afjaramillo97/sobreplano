"""Scraping: reuse extractions by the clean-text hash instead of the raw HTML hash.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Alembic has no rename for constraints, so the unique is renamed with plain SQL.
OLD_UNIQUE = "uq_page_extractions_content_sha256_model"
NEW_UNIQUE = "uq_page_extractions_text_sha256_model"


def upgrade() -> None:
    """Apply this revision.

    Old scraped_pages rows keep text_sha256 NULL. Old extractions keep their HTML hash in
    a column that now means "clean-text hash": they never match again, so the first run
    after this revision re-extracts every page once. Nothing is recomputed.
    """
    op.add_column("scraped_pages", sa.Column("text_sha256", sa.CHAR(length=64), nullable=True))
    # A rename, not drop and create: autogenerate would drop the column and its data.
    op.alter_column("page_extractions", "content_sha256", new_column_name="text_sha256")
    op.execute(f"ALTER TABLE page_extractions RENAME CONSTRAINT {OLD_UNIQUE} TO {NEW_UNIQUE}")


def downgrade() -> None:
    """Revert this revision; drops the clean-text hashes of scraped_pages."""
    op.execute(f"ALTER TABLE page_extractions RENAME CONSTRAINT {NEW_UNIQUE} TO {OLD_UNIQUE}")
    op.alter_column("page_extractions", "text_sha256", new_column_name="content_sha256")
    op.drop_column("scraped_pages", "text_sha256")
