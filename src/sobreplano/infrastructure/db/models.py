"""SQLAlchemy models for catalog, prices and scraping; Alembic is the only owner of the schema."""

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geography, WKBElement, WKTElement
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.pricing import ObservationSource
from sobreplano.domain.scraping import ScrapeRunStatus

# Explicit names so migrations and `alembic check` agree on constraint names.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base carrying the naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    """UUID primary key; the domain generates it, so there is no server default."""

    id: Mapped[UUID] = mapped_column(primary_key=True)


class CreatedAtMixin:
    """Insert timestamp set by the database."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimestampsMixin(CreatedAtMixin):
    """Insert and last-update timestamps; for mutable tables only."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Database values of an enum: the member values, not the member names."""
    return [str(member.value) for member in enum_cls]


def _str_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """A varchar(16) column with a CHECK constraint over the enum values."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        # Without this SQLAlchemy does not emit the CHECK constraint.
        create_constraint=True,
        length=16,
        # Store "medellin", not the member name "MEDELLIN".
        values_callable=_enum_values,
    )


class DeveloperRow(IdMixin, TimestampsMixin, Base):
    """Row of `developers`."""

    __tablename__ = "developers"

    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    website_url: Mapped[str] = mapped_column(Text)


class ProjectRow(IdMixin, TimestampsMixin, Base):
    """Row of `projects`."""

    __tablename__ = "projects"

    developer_id: Mapped[UUID] = mapped_column(ForeignKey("developers.id"))
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    municipality: Mapped[Municipality] = mapped_column(_str_enum(Municipality, "municipality"))
    neighborhood: Mapped[str | None] = mapped_column(Text)
    # Written as a WKT element and read back as WKB (see geo.py); geoalchemy2 adds the GIST index.
    location: Mapped[WKBElement | WKTElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    source_url: Mapped[str] = mapped_column(Text)


class UnitTypeRow(IdMixin, TimestampsMixin, Base):
    """Row of `unit_types`."""

    __tablename__ = "unit_types"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        CheckConstraint(
            "private_area_m2 IS NOT NULL OR built_area_m2 IS NOT NULL", name="area_present"
        ),
        CheckConstraint(
            "(private_area_m2 IS NULL OR private_area_m2 > 0)"
            " AND (built_area_m2 IS NULL OR built_area_m2 > 0)",
            name="area_positive",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(Text)
    private_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    built_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    # Optional since migration 0002: some listings do not publish them.
    bedrooms: Mapped[int | None] = mapped_column(SmallInteger)
    bathrooms: Mapped[int | None] = mapped_column(SmallInteger)


class PriceObservationRow(IdMixin, CreatedAtMixin, Base):
    """Row of `price_observations`; a database trigger makes it append-only (migration 0001)."""

    __tablename__ = "price_observations"
    __table_args__ = (
        UniqueConstraint("unit_type_id", "observed_on"),
        CheckConstraint("price_cop > 0", name="price_positive"),
    )

    unit_type_id: Mapped[UUID] = mapped_column(ForeignKey("unit_types.id"))
    price_cop: Mapped[int] = mapped_column(BigInteger)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_on: Mapped[date] = mapped_column(Date)
    source: Mapped[ObservationSource] = mapped_column(_str_enum(ObservationSource, "source"))
    source_url: Mapped[str] = mapped_column(Text)


class ScrapeRunRow(IdMixin, TimestampsMixin, Base):
    """Row of `scrape_runs`: one pass over one developer's site on one day."""

    __tablename__ = "scrape_runs"

    developer_id: Mapped[UUID] = mapped_column(ForeignKey("developers.id"))
    run_on: Mapped[date] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ScrapeRunStatus] = mapped_column(_str_enum(ScrapeRunStatus, "scrape_run_status"))
    pages_fetched: Mapped[int] = mapped_column(Integer, server_default="0")
    pages_failed: Mapped[int] = mapped_column(Integer, server_default="0")
    observations_recorded: Mapped[int] = mapped_column(Integer, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)


class ScrapedPageRow(IdMixin, CreatedAtMixin, Base):
    """Row of `scraped_pages`: one fetched page; `url` is the canonical URL, never /node/N."""

    __tablename__ = "scraped_pages"
    __table_args__ = (UniqueConstraint("scrape_run_id", "url"),)

    scrape_run_id: Mapped[UUID] = mapped_column(ForeignKey("scrape_runs.id"))
    url: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int] = mapped_column(SmallInteger)
    content_sha256: Mapped[str] = mapped_column(CHAR(64))
    storage_key: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PageExtractionRow(IdMixin, CreatedAtMixin, Base):
    """Row of `page_extractions`: a validated LLM extraction, reused while the HTML hash holds."""

    __tablename__ = "page_extractions"
    # The model is part of the key so switching models re-extracts instead of mixing results.
    __table_args__ = (UniqueConstraint("content_sha256", "model"),)

    content_sha256: Mapped[str] = mapped_column(CHAR(64))
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB)
