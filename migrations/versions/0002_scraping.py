"""Scraping: scrape runs, scraped pages, page extractions; optional bedrooms and bathrooms.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 19:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = ("scrape_runs", "scraped_pages", "page_extractions")


def upgrade() -> None:
    """Apply this revision."""
    op.create_table(
        "scrape_runs",
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("run_on", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "succeeded",
                "failed",
                name="scrape_run_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("pages_fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("pages_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("observations_recorded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["developer_id"],
            ["developers.id"],
            name=op.f("fk_scrape_runs_developer_id_developers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scrape_runs")),
    )
    op.create_table(
        "scraped_pages",
        sa.Column("scrape_run_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["scrape_run_id"],
            ["scrape_runs.id"],
            name=op.f("fk_scraped_pages_scrape_run_id_scrape_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scraped_pages")),
        sa.UniqueConstraint(
            "scrape_run_id", "url", name=op.f("uq_scraped_pages_scrape_run_id_url")
        ),
    )
    op.create_table(
        "page_extractions",
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_extractions")),
        sa.UniqueConstraint(
            "content_sha256", "model", name=op.f("uq_page_extractions_content_sha256_model")
        ),
    )

    # Some listings do not publish bedrooms or bathrooms; never invent a value.
    op.alter_column("unit_types", "bedrooms", existing_type=sa.SmallInteger(), nullable=True)
    op.alter_column("unit_types", "bathrooms", existing_type=sa.SmallInteger(), nullable=True)

    # Same rule as 0001: RLS on with no policies, so the Supabase REST API gets no access.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Revert this revision.

    Fails if any unit type has a NULL bedrooms or bathrooms: there is no value to restore.
    """
    op.alter_column("unit_types", "bathrooms", existing_type=sa.SmallInteger(), nullable=False)
    op.alter_column("unit_types", "bedrooms", existing_type=sa.SmallInteger(), nullable=False)
    op.drop_table("page_extractions")
    op.drop_table("scraped_pages")
    op.drop_table("scrape_runs")
