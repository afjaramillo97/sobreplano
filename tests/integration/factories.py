"""Helpers that persist catalog rows and observations for integration tests."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.domain.pricing import ObservationSource, PriceObservation
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)

# The seed only has Envigado projects, so these two municipalities start empty in every test.
MUNICIPALITY = Municipality.ITAGUI
OTHER_MUNICIPALITY = Municipality.CALDAS


def add_project(
    catalog: SqlCatalogRepository,
    developer: Developer,
    name: str,
    municipality: Municipality = MUNICIPALITY,
) -> Project:
    project = Project(
        id=uuid4(),
        developer_id=developer.id,
        name=name,
        slug=f"proj-{uuid4().hex[:8]}",
        municipality=municipality,
        neighborhood=None,
        location=GeoPoint(lat=6.1735, lon=-75.5925),
        source_url="https://example.com/proyecto",
    )
    catalog.add_project(project)
    return project


def add_unit_type(
    catalog: SqlCatalogRepository,
    project: Project,
    name: str,
    private_area_m2: str | None = "50.00",
    built_area_m2: str | None = None,
) -> UnitType:
    unit_type = UnitType(
        id=uuid4(),
        project_id=project.id,
        name=name,
        private_area_m2=Decimal(private_area_m2) if private_area_m2 else None,
        built_area_m2=Decimal(built_area_m2) if built_area_m2 else None,
        bedrooms=2,
        bathrooms=2,
    )
    catalog.add_unit_type(unit_type)
    return unit_type


def add_price(
    observations: SqlPriceObservationRepository, unit_type: UnitType, day: int, price_cop: int
) -> None:
    observations.add(
        PriceObservation(
            id=uuid4(),
            unit_type_id=unit_type.id,
            price_cop=price_cop,
            observed_at=datetime(2026, 10, day, 15, 0, tzinfo=UTC),
            observed_on=date(2026, 10, day),
            source=ObservationSource.MANUAL,
            source_url="https://example.com/proyecto",
        )
    )
