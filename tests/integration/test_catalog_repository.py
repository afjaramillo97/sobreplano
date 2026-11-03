"""Integration tests for SqlCatalogRepository."""

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository

pytestmark = pytest.mark.integration


def test_developer_round_trip(catalog: SqlCatalogRepository, developer: Developer) -> None:
    assert catalog.get_developer_by_slug(developer.slug) == developer


def test_unknown_slugs_return_none(catalog: SqlCatalogRepository) -> None:
    assert catalog.get_developer_by_slug("no-existe") is None
    assert catalog.get_project_by_slug("no-existe") is None


def test_project_round_trip(catalog: SqlCatalogRepository, project: Project) -> None:
    assert catalog.get_project_by_slug(project.slug) == project


def test_project_without_location_round_trip_and_later_located(
    catalog: SqlCatalogRepository, developer: Developer
) -> None:
    project = Project(
        id=uuid4(),
        developer_id=developer.id,
        name="Ezzenti",
        slug=f"proj-{uuid4().hex[:8]}",
        municipality=Municipality.MEDELLIN,
        neighborhood="Calasanz",
        location=None,
        source_url="https://example.com/ezzenti",
    )
    catalog.add_project(project)
    assert catalog.get_project_by_slug(project.slug) == project

    located = GeoPoint(lat=6.2731, lon=-75.5871)
    catalog.update_project_location(project.id, located)
    assert catalog.get_project_by_slug(project.slug) == replace(project, location=located)


def test_unit_types_are_listed_by_name(
    catalog: SqlCatalogRepository, project: Project, unit_type: UnitType
) -> None:
    other = UnitType(
        id=uuid4(),
        project_id=project.id,
        name="Tipo 0",
        private_area_m2=None,
        built_area_m2=Decimal("70.00"),
        bedrooms=3,
        bathrooms=2,
    )
    catalog.add_unit_type(other)
    assert catalog.list_unit_types(project.id) == [other, unit_type]


def test_unit_types_of_another_project_are_not_listed(
    catalog: SqlCatalogRepository, unit_type: UnitType
) -> None:
    assert catalog.list_unit_types(uuid4()) == []
    assert catalog.list_unit_types(unit_type.project_id) == [unit_type]
