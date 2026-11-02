"""Wires the scrape use case to its adapters; shared by the CLI and the Lambda handler."""

from collections.abc import Callable

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
from sobreplano.infrastructure.scraping.http_fetcher import HttpFetcher
from sobreplano.infrastructure.scraping.londono_gomez import LondonoGomezSite
from sobreplano.infrastructure.scraping.providers import build_extractor, estimate_cost_usd
from sobreplano.infrastructure.scraping.raw_store import build_raw_page_store
from sobreplano.infrastructure.settings import Settings

SITES: dict[str, Callable[[], DeveloperSite]] = {
    LondonoGomezSite.slug: LondonoGomezSite,
}


class ConfigurationError(Exception):
    """Settings or arguments that make a run impossible; raised before any network call."""


def scrape(
    session_factory: sessionmaker[Session],
    *,
    site: DeveloperSite,
    fetcher: PageFetcher,
    store: RawPageStore,
    extractor: ProjectPageExtractor,
    limit: int | None,
    dry_run: bool,
    force: bool = False,
) -> ScrapeReport:
    """Run ScrapeDeveloper in one transaction: committed, or rolled back on a dry run.

    The raw HTML files are written either way; only the database is rolled back. The
    transaction also holds the developer's advisory lock until it ends.
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
        report = use_case.execute(limit=limit, force=force)
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return report


def run_scrape(
    settings: Settings,
    developer: str,
    *,
    limit: int | None,
    dry_run: bool,
    force: bool = False,
    null_pool: bool = False,
) -> ScrapeReport:
    """Build the real adapters from settings and scrape developer once.

    The extractor and the raw store are built before any network or database call,
    so bad configuration fails fast.

    Raises:
        ConfigurationError: if developer is unknown or EXTRACTION_MODEL or RAW_STORE
            is malformed.
    """
    if developer not in SITES:
        raise ConfigurationError(f"unknown developer {developer!r}; known: {sorted(SITES)}")
    try:
        extractor = build_extractor(settings)
        store = build_raw_page_store(settings.raw_store)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
    site = SITES[developer]()
    engine = create_db_engine(settings.database_url, null_pool=null_pool)
    try:
        with HttpFetcher() as fetcher:
            return scrape(
                create_session_factory(engine),
                site=site,
                fetcher=fetcher,
                store=store,
                extractor=extractor,
                limit=limit,
                dry_run=dry_run,
                force=force,
            )
    finally:
        engine.dispose()


def format_summary(report: ScrapeReport, model: str, *, dry_run: bool) -> str:
    """Human summary of a run, with tokens and the estimated cost of new extractions."""
    if report.status is ScrapeRunStatus.SKIPPED:
        return f"status: {report.status}\nreason: {report.error}"
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
