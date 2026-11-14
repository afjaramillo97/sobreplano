"""Integration test: prepare builds the isolated evals database and leaves DATABASE_URL alone."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, func, make_url, select, text
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.listings import ProjectFilters, ProjectSort
from sobreplano.evals.advisor.database import prepare
from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.infrastructure.db.models import ProjectRow
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery

pytestmark = pytest.mark.integration

# Not sobreplano_evals, so the test never wipes a database a developer prepared by hand.
TEST_DATABASE = "sobreplano_evals_test"


@pytest.fixture
def eval_url(engine: Engine) -> Iterator[str]:
    url = engine.url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
    yield url
    admin = create_db_engine(engine.url.render_as_string(hide_password=False))
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
    admin.dispose()


def count_projects(engine: Engine) -> int:
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(ProjectRow)) or 0


def test_prepare_loads_the_catalog_into_its_own_database(engine: Engine, eval_url: str) -> None:
    before = count_projects(engine)

    report = prepare(eval_url)

    assert (report.developers_added, report.projects_added) == (2, 9)
    assert report.observations_recorded == 23
    assert count_projects(engine) == before
    assert make_url(eval_url).database == TEST_DATABASE

    eval_engine = create_db_engine(eval_url)
    try:
        assert count_projects(eval_engine) == 9
        with Session(eval_engine) as session:
            page = SqlProjectListingQuery(session).list_projects(
                filters=ProjectFilters(municipality=Municipality.SABANETA),
                sort=ProjectSort.NAME,
                limit=50,
                offset=0,
            )
    finally:
        eval_engine.dispose()
    assert [item.name for item in page.items] == ["Bosque Prueba", "Mirador del Ejemplo"]


def test_prepare_twice_starts_from_scratch(eval_url: str) -> None:
    prepare(eval_url)
    assert prepare(eval_url).projects_added == 9
