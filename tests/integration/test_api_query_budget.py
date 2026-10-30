"""Query budget: GET /projects runs at most three SELECT statements, however many projects."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pytest
from factories import MUNICIPALITY, add_price, add_project, add_unit_type
from fastapi.testclient import TestClient
from sqlalchemy import Connection, event
from sqlalchemy.engine.interfaces import DBAPICursor, ExecutionContext
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)

pytestmark = pytest.mark.integration

MAX_SELECTS = 3


@contextmanager
def count_selects(session: Session) -> Generator[list[str]]:
    """Collect the SELECT statements the session's connection executes.

    BEGIN and SAVEPOINT are not counted: they come from the session, not from the listing.
    """
    connection = session.get_bind()
    assert isinstance(connection, Connection)
    statements: list[str] = []

    def record(
        _conn: Connection,
        _cursor: DBAPICursor,
        statement: str,
        _parameters: Any,
        _context: ExecutionContext | None,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(connection, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(connection, "before_cursor_execute", record)


def test_listing_does_not_grow_with_projects_or_unit_types(
    client: TestClient,
    session: Session,
    catalog: SqlCatalogRepository,
    observations: SqlPriceObservationRepository,
    developer: Developer,
) -> None:
    for name in ("Proyecto A", "Proyecto B", "Proyecto C"):
        project = add_project(catalog, developer, name)
        for unit_name in ("Tipo 01", "Tipo 02"):
            unit_type = add_unit_type(catalog, project, unit_name)
            add_price(observations, unit_type, 27, 400_000_000)
            add_price(observations, unit_type, 28, 450_000_000)

    with count_selects(session) as statements:
        response = client.get("/projects", params={"municipality": MUNICIPALITY})

    body = response.json()
    assert len(body["items"]) == 3
    assert all(len(item["unit_types"]) == 2 for item in body["items"])
    assert 0 < len(statements) <= MAX_SELECTS, statements
