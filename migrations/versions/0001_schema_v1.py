"""Schema v1: catalog tables, append-only price observations, RLS.

Revision ID: 0001
Revises:
Create Date: 2026-10-28 12:43:52.256988
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RLS_TABLES = ("developers", "projects", "unit_types", "price_observations", "alembic_version")


def upgrade() -> None:
    """Apply this revision."""
    # Supabase keeps extensions out of `public`; its default search_path includes `extensions`.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions")
    op.create_table(
        "developers",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("website_url", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_developers")),
        sa.UniqueConstraint("slug", name=op.f("uq_developers_slug")),
    )
    op.create_geospatial_table(
        "projects",
        sa.Column("developer_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "municipality",
            sa.Enum(
                "medellin",
                "bello",
                "itagui",
                "envigado",
                "sabaneta",
                "la_estrella",
                "caldas",
                "copacabana",
                "girardota",
                "barbosa",
                name="municipality",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("neighborhood", sa.Text(), nullable=True),
        sa.Column(
            "location",
            Geography(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeogFromText",
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
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
            ["developer_id"], ["developers.id"], name=op.f("fk_projects_developer_id_developers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("slug", name=op.f("uq_projects_slug")),
    )
    op.create_geospatial_index(
        "idx_projects_location",
        "projects",
        ["location"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_table(
        "unit_types",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("private_area_m2", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("built_area_m2", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("bedrooms", sa.SmallInteger(), nullable=False),
        sa.Column("bathrooms", sa.SmallInteger(), nullable=False),
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
        sa.CheckConstraint(
            "(private_area_m2 IS NULL OR private_area_m2 > 0)"
            " AND (built_area_m2 IS NULL OR built_area_m2 > 0)",
            name=op.f("ck_unit_types_area_positive"),
        ),
        sa.CheckConstraint(
            "private_area_m2 IS NOT NULL OR built_area_m2 IS NOT NULL",
            name=op.f("ck_unit_types_area_present"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_unit_types_project_id_projects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_unit_types")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_unit_types_project_id_name")),
    )
    op.create_table(
        "price_observations",
        sa.Column("unit_type_id", sa.Uuid(), nullable=False),
        sa.Column("price_cop", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "scraper",
                name="source",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price_cop > 0", name=op.f("ck_price_observations_price_positive")),
        sa.ForeignKeyConstraint(
            ["unit_type_id"],
            ["unit_types.id"],
            name=op.f("fk_price_observations_unit_type_id_unit_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_observations")),
        sa.UniqueConstraint(
            "unit_type_id",
            "observed_on",
            name=op.f("uq_price_observations_unit_type_id_observed_on"),
        ),
    )

    # RLS on with no policies: the Supabase REST API gets no access, while the app, which
    # connects as the table owner, is unaffected. alembic_version is created by Alembic before
    # this revision runs.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # Append-only (constitution, principle 2): enforced in the database so psql and scripts
    # cannot rewrite history either. Row triggers do not fire on TRUNCATE, hence the second one.
    op.execute(
        """
        CREATE FUNCTION prevent_price_observation_changes() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            RAISE EXCEPTION 'price_observations is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER price_observations_no_update_delete
        BEFORE UPDATE OR DELETE ON price_observations
        FOR EACH ROW EXECUTE FUNCTION prevent_price_observation_changes()
        """
    )
    op.execute(
        """
        CREATE TRIGGER price_observations_no_truncate
        BEFORE TRUNCATE ON price_observations
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_price_observation_changes()
        """
    )


def downgrade() -> None:
    """Revert this revision."""
    op.execute("ALTER TABLE alembic_version DISABLE ROW LEVEL SECURITY")
    op.drop_table("price_observations")
    op.drop_table("unit_types")
    op.drop_geospatial_index(
        "idx_projects_location",
        table_name="projects",
        postgresql_using="gist",
        column_name="location",
    )
    op.drop_geospatial_table("projects")
    op.drop_table("developers")
    op.execute("DROP FUNCTION prevent_price_observation_changes()")
