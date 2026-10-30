"""SQLAlchemy models for schema v1; Alembic is the only owner of the schema."""

import enum
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from geoalchemy2 import Geography, WKBElement, WKTElement
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.pricing import ObservationSource

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
    bedrooms: Mapped[int] = mapped_column(SmallInteger)
    bathrooms: Mapped[int] = mapped_column(SmallInteger)


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
