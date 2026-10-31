"""Integration tests for the rules the database itself enforces."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.domain.errors import DuplicateObservationError
from sobreplano.domain.pricing import ObservationSource, PriceObservation
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)

pytestmark = pytest.mark.integration

TABLES = {
    "developers",
    "projects",
    "unit_types",
    "price_observations",
    "alembic_version",
    "scrape_runs",
    "scraped_pages",
    "page_extractions",
}


def make_observation(unit_type: UnitType, price_cop: int = 320_000_000) -> PriceObservation:
    return PriceObservation(
        id=uuid4(),
        unit_type_id=unit_type.id,
        price_cop=price_cop,
        observed_at=datetime(2026, 10, 28, 15, 0, tzinfo=UTC),
        observed_on=date(2026, 10, 28),
        source=ObservationSource.MANUAL,
        source_url="https://example.com/proyecto",
    )


@pytest.fixture
def observation(
    observations: SqlPriceObservationRepository, unit_type: UnitType
) -> PriceObservation:
    observation = make_observation(unit_type)
    observations.add(observation)
    return observation


def test_update_is_rejected(session: Session, observation: PriceObservation) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(
            text("UPDATE price_observations SET price_cop = 1 WHERE id = :id"),
            {"id": observation.id},
        )


def test_delete_is_rejected(session: Session, observation: PriceObservation) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(
            text("DELETE FROM price_observations WHERE id = :id"), {"id": observation.id}
        )


def test_truncate_is_rejected(session: Session, observation: PriceObservation) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("TRUNCATE price_observations"))


def test_second_observation_on_the_same_day_is_rejected(
    observations: SqlPriceObservationRepository, unit_type: UnitType, observation: PriceObservation
) -> None:
    # The repository translates the violation; the database constraint is what rejects it.
    with pytest.raises(DuplicateObservationError) as raised:
        observations.add(make_observation(unit_type, price_cop=330_000_000))
    assert isinstance(raised.value.__cause__, IntegrityError)


def test_unit_type_without_areas_is_rejected(session: Session, project: Project) -> None:
    # The domain entity would refuse this, so the row goes in with raw SQL.
    with pytest.raises(IntegrityError, match="ck_unit_types_area_present"):
        session.execute(
            text(
                "INSERT INTO unit_types (id, project_id, name, bedrooms, bathrooms)"
                " VALUES (:id, :project_id, 'Sin areas', 1, 1)"
            ),
            {"id": uuid4(), "project_id": project.id},
        )


def test_row_level_security_is_enabled_everywhere(session: Session) -> None:
    rows = session.execute(
        text(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relname = ANY(:tables)"
        ),
        {"tables": sorted(TABLES)},
    ).all()
    assert {name: enabled for name, enabled in rows} == dict.fromkeys(TABLES, True)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(6.2442, -75.5812), (6.1517, -75.6167), (6.34, -75.55)],
)
def test_saved_point_comes_back_with_the_same_coordinates(
    catalog: SqlCatalogRepository, developer: Developer, lat: float, lon: float
) -> None:
    project = Project(
        id=uuid4(),
        developer_id=developer.id,
        name="Proyecto geo",
        slug=f"geo-{uuid4().hex[:8]}",
        municipality=Municipality.MEDELLIN,
        neighborhood=None,
        location=GeoPoint(lat=lat, lon=lon),
        source_url="https://example.com/geo",
    )
    catalog.add_project(project)
    found = catalog.get_project_by_slug(project.slug)
    assert found is not None
    assert found.location.lat == pytest.approx(lat)  # pyright: ignore[reportUnknownMemberType]
    assert found.location.lon == pytest.approx(lon)  # pyright: ignore[reportUnknownMemberType]
