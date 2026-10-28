"""Integration test: loading a seed twice adds rows only the first time."""

import copy
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sobreplano.infrastructure.db.models import (
    DeveloperRow,
    PriceObservationRow,
    ProjectRow,
    UnitTypeRow,
)
from sobreplano.interface.cli.seed import SeedReport, run_seed
from sobreplano.interface.cli.seed_schema import SeedFile

pytestmark = pytest.mark.integration


def fictitious_seed() -> SeedFile:
    suffix = uuid4().hex[:8]
    unit_type: dict[str, Any] = {
        "private_area_m2": 50,
        "bedrooms": 2,
        "bathrooms": 1,
        "observation": {
            "price_cop": 300000000,
            "observed_at": "2026-10-28T10:00:00-05:00",
            "source_url": "https://example.com/p",
        },
    }
    data: dict[str, Any] = {
        "projects": [
            {
                "developer": {
                    "name": "Ficticia",
                    "slug": f"dev-{suffix}",
                    "website_url": "https://example.com",
                },
                "name": f"Proyecto {i}",
                "slug": f"proj-{suffix}-{i}",
                "municipality": "bello",
                "lat": 6.33,
                "lon": -75.56,
                "source_url": "https://example.com/p",
                "unit_types": [copy.deepcopy(unit_type) | {"name": "Tipo A"}],
            }
            for i in range(3)
        ]
    }
    return SeedFile.model_validate(data)


def counts(session: Session) -> list[int]:
    """Row counts of developers, projects, unit types and observations."""
    tables = (DeveloperRow, ProjectRow, UnitTypeRow, PriceObservationRow)
    return [session.scalar(select(func.count()).select_from(table)) or 0 for table in tables]


def test_seed_is_idempotent(session: Session) -> None:
    seed = fictitious_seed()
    before = counts(session)

    first = run_seed(session, seed)
    after_first = counts(session)
    second = run_seed(session, seed)

    assert first == SeedReport(
        developers_added=1, projects_added=3, unit_types_added=3, observations_recorded=3
    )
    assert after_first == [b + a for b, a in zip(before, [1, 3, 3, 3], strict=True)]
    assert second == SeedReport()
    assert counts(session) == after_first
