"""Prompt versions: in page_extractions (part of the reuse key) and in llm_usage.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_UNIQUE = "uq_page_extractions_text_sha256_model"
NEW_UNIQUE = "uq_page_extractions_text_sha256_model_prompt_version"
LEGACY = "legacy"


def upgrade() -> None:
    """Apply this revision.

    Existing extractions get prompt_version 'legacy'. The extractor never asks for that
    version, so the first run after this revision re-extracts every page once.
    """
    # The default only fills the existing rows; it is dropped so the code always sets it.
    op.add_column(
        "page_extractions",
        sa.Column("prompt_version", sa.Text(), nullable=False, server_default=LEGACY),
    )
    op.alter_column("page_extractions", "prompt_version", server_default=None)
    op.drop_constraint(OLD_UNIQUE, "page_extractions", type_="unique")
    op.create_unique_constraint(
        NEW_UNIQUE, "page_extractions", ["text_sha256", "model", "prompt_version"]
    )
    op.add_column("llm_usage", sa.Column("prompt_version", sa.Text(), nullable=True))


def downgrade() -> None:
    """Revert this revision; deletes the extractions made with a versioned prompt.

    Without the version, an old and a new extraction of the same text and model would
    collide on the previous unique.
    """
    op.drop_column("llm_usage", "prompt_version")
    op.execute(f"DELETE FROM page_extractions WHERE prompt_version <> '{LEGACY}'")
    op.drop_constraint(NEW_UNIQUE, "page_extractions", type_="unique")
    op.create_unique_constraint(OLD_UNIQUE, "page_extractions", ["text_sha256", "model"])
    op.drop_column("page_extractions", "prompt_version")
