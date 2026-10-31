"""Use case: one daily scrape of one developer's site, from listing to price observations."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sobreplano.application.record_price_observation import (
    BOGOTA,
    RecordPriceObservation,
    RecordResult,
)
from sobreplano.domain.catalog import Developer, Project, UnitType
from sobreplano.domain.errors import (
    DomainValidationError,
    ExtractionError,
    FetchError,
    PageParseError,
)
from sobreplano.domain.ports import (
    CatalogRepository,
    DeveloperSite,
    PageFetcher,
    ProjectPageExtractor,
    RawPageStore,
    ScrapeRunRepository,
)
from sobreplano.domain.pricing import ObservationSource
from sobreplano.domain.scraping import (
    ExtractionResult,
    FetchedPage,
    ParsedProjectPage,
    RejectedUnitType,
    ScrapedPage,
    ScrapeRunStatus,
    ValidUnitType,
    content_sha256,
    normalize_unit_type_name,
    validate_unit_type,
)

logger = logging.getLogger(__name__)

# What makes one page fail without stopping the run; anything else is a bug and propagates.
PAGE_ERRORS = (FetchError, PageParseError, ExtractionError, DomainValidationError)


@dataclass
class ScrapeReport:
    """Counters of one run, for the CLI summary; tokens only count new extractions."""

    status: ScrapeRunStatus = ScrapeRunStatus.RUNNING
    error: str | None = None
    pages_listed: int = 0
    pages_fetched: int = 0
    pages_out_of_scope: int = 0
    pages_failed: int = 0
    projects_added: int = 0
    unit_types_added: int = 0
    unit_types_valid: int = 0
    unit_types_rejected: int = 0
    observations_recorded: int = 0
    observations_already_recorded: int = 0
    extractions_new: int = 0
    extractions_reused: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    pages_with_price: int = 0
    failures: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class ScrapeDeveloper:
    """Scrapes one developer: listing, project pages, extraction and one price per unit type.

    Does not commit: the caller owns the transaction (and rolls back on a dry run).
    """

    site: DeveloperSite
    fetcher: PageFetcher
    store: RawPageStore
    extractor: ProjectPageExtractor
    runs: ScrapeRunRepository
    catalog: CatalogRepository
    record: RecordPriceObservation
    now: Callable[[], datetime] = lambda: datetime.now(UTC)

    def execute(self, limit: int | None = None) -> ScrapeReport:
        """Run the scrape over at most `limit` project pages (all of them when None).

        A page that fails is counted and logged, and the run goes on. The run ends SUCCEEDED
        if at least one page has a price for today, recorded now or earlier the same day;
        otherwise FAILED, with the reason in scrape_runs.error.
        """
        report = ScrapeReport()
        developer = self._developer()
        run = self.runs.start(developer.id, self.now().astimezone(BOGOTA).date())

        try:
            listing = self.fetcher.fetch(self.site.listing_url)
            if listing.status != 200:
                raise FetchError(f"listing {self.site.listing_url} answered {listing.status}")
        except FetchError as error:
            report.status, report.error = ScrapeRunStatus.FAILED, str(error)
        else:
            urls = self.site.project_urls(listing.html)
            urls = urls if limit is None else urls[:limit]
            report.pages_listed = len(urls)
            seen: set[str] = set()
            for url in urls:
                try:
                    self._scrape_page(url, developer, run.id, seen, report)
                except PAGE_ERRORS as error:
                    report.pages_failed += 1
                    report.failures.append(f"{url}: {error}")
                    logger.warning("page failed: %s: %s", url, error)
            if report.pages_with_price > 0:
                report.status = ScrapeRunStatus.SUCCEEDED
            else:
                report.status = ScrapeRunStatus.FAILED
                report.error = f"no page recorded a price ({report.pages_failed} failed)"

        self.runs.finish(
            replace(
                run,
                status=report.status,
                finished_at=self.now(),
                pages_fetched=report.pages_fetched,
                pages_failed=report.pages_failed,
                observations_recorded=report.observations_recorded,
                error=report.error,
            )
        )
        return report

    def _developer(self) -> Developer:
        developer = self.catalog.get_developer_by_slug(self.site.slug)
        if developer is None:
            developer = Developer(
                id=uuid4(),
                name=self.site.name,
                slug=self.site.slug,
                website_url=self.site.website_url,
            )
            self.catalog.add_developer(developer)
        return developer

    def _scrape_page(
        self,
        url: str,
        developer: Developer,
        run_id: UUID,
        seen: set[str],
        report: ScrapeReport,
    ) -> None:
        page = self.fetcher.fetch(url)
        if page.status != 200:
            raise FetchError(f"answered {page.status}")
        parsed = self.site.parse_project(page)
        # Out of scope, or a second /node/N with the same canonical page: never stored or
        # extracted, only counted.
        if parsed is None or parsed.canonical_url in seen:
            report.pages_out_of_scope += 1
            return
        seen.add(parsed.canonical_url)

        sha256 = content_sha256(page.html)
        self.runs.record_page(
            run_id,
            ScrapedPage(
                url=parsed.canonical_url,
                http_status=page.status,
                content_sha256=sha256,
                storage_key=self.store.save(self.site.slug, page),
                fetched_at=page.fetched_at,
            ),
        )
        report.pages_fetched += 1

        extraction = self._extraction(sha256, parsed.text, report)
        project = self._project(developer, parsed, extraction, report)
        if self._record_prices(project, page, parsed, extraction, report):
            report.pages_with_price += 1

    def _extraction(self, sha256: str, text: str, report: ScrapeReport) -> ExtractionResult:
        # Same HTML and same model: reuse, so an unchanged page costs no tokens.
        stored = self.runs.find_extraction(sha256, self.extractor.model)
        if stored is not None:
            report.extractions_reused += 1
            return stored
        extraction = self.extractor.extract(text)
        self.runs.save_extraction(sha256, extraction)
        report.extractions_new += 1
        report.input_tokens += extraction.input_tokens
        report.output_tokens += extraction.output_tokens
        return extraction

    def _project(
        self,
        developer: Developer,
        parsed: ParsedProjectPage,
        extraction: ExtractionResult,
        report: ScrapeReport,
    ) -> Project:
        project = self.catalog.get_project_by_slug(parsed.slug)
        if project is None:
            project = Project(
                id=uuid4(),
                developer_id=developer.id,
                name=extraction.project.name,
                slug=parsed.slug,
                municipality=parsed.municipality,
                neighborhood=extraction.project.neighborhood,
                location=parsed.location,
                source_url=parsed.canonical_url,
            )
            self.catalog.add_project(project)
            report.projects_added += 1
        elif project.developer_id != developer.id:
            # Project slugs are global; another developer's project must not get these prices.
            raise DomainValidationError(f"slug {parsed.slug} belongs to another developer")
        return project

    def _record_prices(
        self,
        project: Project,
        page: FetchedPage,
        parsed: ParsedProjectPage,
        extraction: ExtractionResult,
        report: ScrapeReport,
    ) -> bool:
        """Record one price per valid unit type; True if the page has any price for today."""
        existing = {
            normalize_unit_type_name(unit_type.name): unit_type
            for unit_type in self.catalog.list_unit_types(project.id)
        }
        priced = False
        for extracted in extraction.project.unit_types:
            valid = validate_unit_type(extracted)
            if isinstance(valid, RejectedUnitType):
                report.unit_types_rejected += 1
                logger.info(
                    "unit type rejected: %s %r: %s", parsed.canonical_url, valid.name, valid.reason
                )
                continue
            report.unit_types_valid += 1
            for warning in valid.warnings:
                logger.info("unit type %r at %s: %s", valid.name, parsed.canonical_url, warning)

            unit_type = self._unit_type(project, valid, existing, parsed.canonical_url, report)
            result = self.record.execute(
                unit_type_id=unit_type.id,
                price_cop=valid.price_cop,
                observed_at=page.fetched_at,
                source=ObservationSource.SCRAPER,
                source_url=parsed.canonical_url,
            )
            if result is RecordResult.RECORDED:
                report.observations_recorded += 1
            else:
                report.observations_already_recorded += 1
            priced = True
        return priced

    def _unit_type(
        self,
        project: Project,
        valid: ValidUnitType,
        existing: dict[str, UnitType],
        url: str,
        report: ScrapeReport,
    ) -> UnitType:
        key = normalize_unit_type_name(valid.name)
        unit_type = existing.get(key)
        if unit_type is None:
            unit_type = UnitType(
                id=uuid4(),
                project_id=project.id,
                name=valid.name,
                private_area_m2=valid.private_area_m2,
                built_area_m2=valid.built_area_m2,
                bedrooms=valid.bedrooms,
                bathrooms=valid.bathrooms,
            )
            self.catalog.add_unit_type(unit_type)
            existing[key] = unit_type
            report.unit_types_added += 1
        elif (unit_type.built_area_m2, unit_type.private_area_m2) != (
            valid.built_area_m2,
            valid.private_area_m2,
        ):
            # v1 creates unit types once; changes are only logged (SPEC 04).
            logger.info(
                "unit type %r at %s changed area: stored %s/%s, page %s/%s",
                valid.name,
                url,
                unit_type.built_area_m2,
                unit_type.private_area_m2,
                valid.built_area_m2,
                valid.private_area_m2,
            )
        return unit_type
