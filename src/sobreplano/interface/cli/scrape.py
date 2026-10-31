"""Scrape one developer's site once: python -m sobreplano.interface.cli.scrape londono-gomez."""

import argparse
import logging
from collections.abc import Callable, Sequence

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.application.record_price_observation import RecordPriceObservation
from sobreplano.application.scrape_developer import ScrapeDeveloper, ScrapeReport
from sobreplano.domain.ports import (
    DeveloperSite,
    PageFetcher,
    ProjectPageExtractor,
    RawPageStore,
)
from sobreplano.domain.scraping import ScrapeRunStatus
from sobreplano.infrastructure.db.catalog_repository import SqlCatalogRepository
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)
from sobreplano.infrastructure.db.scrape_run_repository import SqlScrapeRunRepository
from sobreplano.infrastructure.scraping.file_store import FileRawPageStore
from sobreplano.infrastructure.scraping.http_fetcher import HttpFetcher
from sobreplano.infrastructure.scraping.londono_gomez import LondonoGomezSite
from sobreplano.infrastructure.scraping.providers import build_extractor, estimate_cost_usd
from sobreplano.infrastructure.settings import load_settings

SITES: dict[str, Callable[[], DeveloperSite]] = {
    LondonoGomezSite.slug: LondonoGomezSite,
}


def scrape(
    session_factory: sessionmaker[Session],
    *,
    site: DeveloperSite,
    fetcher: PageFetcher,
    store: RawPageStore,
    extractor: ProjectPageExtractor,
    limit: int | None,
    dry_run: bool,
) -> ScrapeReport:
    """Run ScrapeDeveloper in one transaction: committed, or rolled back on a dry run.

    The raw HTML files are written either way; only the database is rolled back.
    """
    with session_factory() as session:
        use_case = ScrapeDeveloper(
            site=site,
            fetcher=fetcher,
            store=store,
            extractor=extractor,
            runs=SqlScrapeRunRepository(session),
            catalog=SqlCatalogRepository(session),
            record=RecordPriceObservation(SqlPriceObservationRepository(session)),
        )
        report = use_case.execute(limit=limit)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return report


def format_summary(report: ScrapeReport, model: str, *, dry_run: bool) -> str:
    """Human summary of a run, with tokens and the estimated cost of new extractions."""
    cost = estimate_cost_usd(model, report.input_tokens, report.output_tokens)
    lines = [
        f"status: {report.status}" + (" (dry run, rolled back)" if dry_run else ""),
        f"pages: {report.pages_listed} listed, {report.pages_fetched} fetched,"
        f" {report.pages_out_of_scope} out of scope, {report.pages_failed} failed",
        f"projects added: {report.projects_added}, unit types added: {report.unit_types_added}",
        f"unit types: {report.unit_types_valid} valid, {report.unit_types_rejected} rejected",
        f"observations: {report.observations_recorded} recorded,"
        f" {report.observations_already_recorded} already recorded today",
        f"extractions: {report.extractions_new} new, {report.extractions_reused} reused",
        f"tokens ({model}): {report.input_tokens} input, {report.output_tokens} output",
        "estimated cost: " + ("unknown model price" if cost is None else f"{cost:.4f} USD"),
    ]
    if report.error:
        lines.append(f"error: {report.error}")
    lines.extend(f"failed: {failure}" for failure in report.failures)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; exits 0 when the run succeeds, 1 when it fails, 2 on bad configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("developer", choices=sorted(SITES))
    parser.add_argument("--limit", type=int, default=None, help="at most N project pages")
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and extract, then roll the database back"
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # One line per HTTP request from httpx and openai is noise next to the run's own log.
    for noisy in ("httpx", "httpx2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        settings = load_settings()
        extractor = build_extractor(settings)
    except (ValidationError, ValueError) as error:
        print(f"bad configuration: {error}")
        return 2

    session_factory = create_session_factory(create_db_engine(settings.database_url))
    with HttpFetcher() as fetcher:
        report = scrape(
            session_factory,
            site=SITES[args.developer](),
            fetcher=fetcher,
            store=FileRawPageStore(),
            extractor=extractor,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    print(format_summary(report, extractor.model, dry_run=args.dry_run))
    return 0 if report.status is ScrapeRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
