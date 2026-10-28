"""Load seeds/projects.json into the database; safe to run more than once."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from sobreplano.application.record_price_observation import (
    RecordPriceObservation,
    RecordResult,
)
from sobreplano.domain.pricing import ObservationSource
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.interface.cli.seed_schema import SeedFile

DEFAULT_SEED_PATH = Path("seeds/projects.json")


@dataclass
class SeedReport:
    """How many rows a seed run added; zeros everywhere on a repeated run."""

    developers_added: int = 0
    projects_added: int = 0
    unit_types_added: int = 0
    observations_recorded: int = 0


def load_seed(path: Path) -> SeedFile:
    """Read and validate the seed file.

    Raises:
        FileNotFoundError: if path does not exist.
        pydantic.ValidationError: if the content breaks the schema or the domain rules.
    """
    return SeedFile.model_validate_json(path.read_text(encoding="utf-8"))


def run_seed(session: Session, seed: SeedFile) -> SeedReport:
    """Insert what is missing, matching developers and projects by slug.

    Does not commit. Observations go through the use case, so a second run on the same day
    records nothing.
    """
    catalog = SqlCatalogRepository(session)
    record = RecordPriceObservation(SqlPriceObservationRepository(session))
    report = SeedReport()
    for seed_project in seed.projects:
        developer = catalog.get_developer_by_slug(seed_project.developer.slug)
        if developer is None:
            developer = seed_project.to_developer()
            catalog.add_developer(developer)
            report.developers_added += 1

        project = catalog.get_project_by_slug(seed_project.slug)
        if project is None:
            project = seed_project.to_project(developer.id)
            catalog.add_project(project)
            report.projects_added += 1

        existing = {unit_type.name: unit_type for unit_type in catalog.list_unit_types(project.id)}
        for seed_unit_type in seed_project.unit_types:
            unit_type = existing.get(seed_unit_type.name)
            if unit_type is None:
                unit_type = seed_unit_type.to_unit_type(project.id)
                catalog.add_unit_type(unit_type)
                report.unit_types_added += 1

            observation = seed_unit_type.observation
            result = record.execute(
                unit_type_id=unit_type.id,
                price_cop=observation.price_cop,
                observed_at=observation.observed_at,
                source=ObservationSource.MANUAL,
                source_url=observation.source_url,
            )
            if result is RecordResult.RECORDED:
                report.observations_recorded += 1
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: validate the file, then load it in a single transaction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_PATH)
    args = parser.parse_args(argv)

    try:
        seed = load_seed(args.file)
    except FileNotFoundError:
        print(f"seed file not found: {args.file}")
        return 1
    except ValidationError as error:
        print(f"invalid seed file {args.file}:\n{error}")
        return 1

    session_factory = create_session_factory(create_db_engine())
    with session_factory.begin() as session:
        report = run_seed(session, seed)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
