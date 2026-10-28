"""Fixtures for integration tests: one transaction per test, rolled back at the end."""

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Engine for DATABASE_URL; fails loudly if the variable is missing."""
    engine = create_db_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session inside an outer transaction that is always rolled back.

    The price_observations trigger blocks TRUNCATE, so tables cannot be cleaned between tests.
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        # Savepoints let a test recover from an expected constraint error.
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def catalog(session: Session) -> SqlCatalogRepository:
    return SqlCatalogRepository(session)


@pytest.fixture
def observations(session: Session) -> SqlPriceObservationRepository:
    return SqlPriceObservationRepository(session)


@pytest.fixture
def developer(catalog: SqlCatalogRepository) -> Developer:
    """A persisted developer with a random slug, so it never clashes with seed data."""
    developer = Developer(
        id=uuid4(),
        name="Constructora de prueba",
        slug=f"dev-{uuid4().hex[:8]}",
        website_url="https://example.com",
    )
    catalog.add_developer(developer)
    return developer


@pytest.fixture
def project(catalog: SqlCatalogRepository, developer: Developer) -> Project:
    project = Project(
        id=uuid4(),
        developer_id=developer.id,
        name="Proyecto de prueba",
        slug=f"proj-{uuid4().hex[:8]}",
        municipality=Municipality.SABANETA,
        neighborhood="Aves María",
        location=GeoPoint(lat=6.1517, lon=-75.6167),
        source_url="https://example.com/proyecto",
    )
    catalog.add_project(project)
    return project


@pytest.fixture
def unit_type(catalog: SqlCatalogRepository, project: Project) -> UnitType:
    unit_type = UnitType(
        id=uuid4(),
        project_id=project.id,
        name="Tipo A",
        private_area_m2=Decimal("55.50"),
        built_area_m2=None,
        bedrooms=2,
        bathrooms=2,
    )
    catalog.add_unit_type(unit_type)
    return unit_type
