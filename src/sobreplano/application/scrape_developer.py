"""Use case: one daily scrape of one developer's site, from listing to price observations."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sobreplano.application.record_price_observation import (
    BOGOTA,
    RecordPriceObservation,
    RecordResult,
)
from sobreplano.domain.catalog import Developer, GeoPoint, Project, UnitType
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
    dedupe_unit_types,
    normalize_unit_type_name,
    text_sha256,
    unit_types_with_same_area,
    validate_unit_type,
)

logger = logging.getLogger(__name__)

# What makes one page fail without stopping the run; anything else is a bug and propagates.
PAGE_ERRORS = (FetchError, PageParseError, ExtractionError, DomainValidationError)


@dataclass
class ScrapeReport:
    """Counters of one run, for the CLI summary; tokens only count new extractions."""

    status: ScrapeRunStatus = ScrapeRunStatus.RUNNING
    error: str | None = None  # why the run failed, or why it was skipped
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

    def execute(self, limit: int | None = None, *, force: bool = False) -> ScrapeReport:
        """Run the scrape over at most `limit` project pages (all of them when None).

        Before any request the run ends SKIPPED if another run of this developer holds
        the lock, or if one already succeeded today (Bogotá); force skips only the
        second check. A page that fails is counted and logged, and the run goes on. The
        run ends SUCCEEDED if at least one page has a price for today, recorded now or
        earlier the same day; otherwise FAILED, with the reason in scrape_runs.error.
        """
        report = ScrapeReport()
        developer = self._developer()
        today = self.now().astimezone(BOGOTA).date()
        skip_reason = self._skip_reason(developer.id, today, force=force)
        run = self.runs.start(developer.id, today)

        if skip_reason is not None:
            report.status, report.error = ScrapeRunStatus.SKIPPED, skip_reason
            logger.info("run skipped: %s", skip_reason)
        else:
            self._scrape(developer, run.id, limit, report)

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

    def _skip_reason(self, developer_id: UUID, today: date, *, force: bool) -> str | None:
        # The lock comes first, so the "succeeded today" check cannot race another run.
        if not self.runs.try_lock(developer_id):
            return "another run of this developer is in progress"
        if not force and self.runs.has_succeeded(developer_id, today):
            return f"a run already succeeded on {today.isoformat()}"
        return None

    def _scrape(
        self, developer: Developer, run_id: UUID, limit: int | None, report: ScrapeReport
    ) -> None:
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
                    self._scrape_page(url, developer, run_id, seen, report)
                except PAGE_ERRORS as error:
                    report.pages_failed += 1
                    report.failures.append(f"{url}: {error}")
                    logger.warning("page failed: %s: %s", url, error)
            if report.pages_with_price > 0:
                report.status = ScrapeRunStatus.SUCCEEDED
            else:
                report.status = ScrapeRunStatus.FAILED
                report.error = f"no page recorded a price ({report.pages_failed} failed)"

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

        text_hash = text_sha256(parsed.text)
        self.runs.record_page(
            run_id,
            ScrapedPage(
                url=parsed.canonical_url,
                http_status=page.status,
                content_sha256=content_sha256(page.html),
                text_sha256=text_hash,
                storage_key=self.store.save(self.site.slug, page),
                fetched_at=page.fetched_at,
            ),
        )
        report.pages_fetched += 1

        extraction = self._extraction(text_hash, parsed.text, report)
        project = self._project(developer, parsed, extraction, report)
        if self._record_prices(project, page, parsed, extraction, report):
            report.pages_with_price += 1

    def _extraction(self, text_hash: str, text: str, report: ScrapeReport) -> ExtractionResult:
        # Same clean text, model and prompt: reuse, so an unchanged page costs no tokens.
        stored = self.runs.find_extraction(
            text_hash, self.extractor.model, self.extractor.prompt_version
        )
        if stored is not None:
            report.extractions_reused += 1
            return stored
        extraction = self.extractor.extract(text)
        self.runs.save_extraction(text_hash, extraction)
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
            # A hand-loaded seed project has its own slug but the page's URL.
            project = self.catalog.get_project_by_source_url(parsed.canonical_url)
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
        else:
            project = self._refresh_location(project, parsed.location, parsed.canonical_url)
        if project.location is None:
            logger.warning("no location for %s: no map link nor manual entry", parsed.canonical_url)
        return project

    def _refresh_location(self, project: Project, found: GeoPoint | None, url: str) -> Project:
        """Store a location the page now publishes; a changed one is only logged."""
        if found is None or found == project.location:
            return project
        if project.location is None:
            self.catalog.update_project_location(project.id, found)
            logger.info("location published for %s: %s", url, found)
            return replace(project, location=found)
        # Like unit type areas (SPEC 04): a stored location is never overwritten.
        logger.info("location of %s changed: stored %s, page %s", url, project.location, found)
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
        accepted: list[ValidUnitType] = []
        for extracted in extraction.project.unit_types:
            checked = validate_unit_type(extracted)
            if isinstance(checked, RejectedUnitType):
                report.unit_types_rejected += 1
                logger.info(
                    "unit type rejected: %s %r: %s",
                    parsed.canonical_url,
                    checked.name,
                    checked.reason,
                )
            else:
                accepted.append(checked)
        # Before counting: a unit type the page lists twice is one unit type, not two.
        deduped = dedupe_unit_types(accepted)
        if len(deduped) < len(accepted):
            logger.info(
                "%s: %d unit types listed twice, kept once",
                parsed.canonical_url,
                len(accepted) - len(deduped),
            )

        unit_types = self._unit_types(project, deduped, parsed.canonical_url, report)
        priced = False
        for valid, unit_type in zip(deduped, unit_types, strict=True):
            report.unit_types_valid += 1
            for warning in valid.warnings:
                logger.info("unit type %r at %s: %s", valid.name, parsed.canonical_url, warning)

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

    def _unit_types(
        self, project: Project, page: list[ValidUnitType], url: str, report: ScrapeReport
    ) -> list[UnitType]:
        """The stored unit type of each page unit type: by name, else by area, else new.

        Names are matched for the whole page first, so an area match never takes a row
        that another unit type of the same page matches by name.
        """
        stored = self.catalog.list_unit_types(project.id)
        by_name = {normalize_unit_type_name(unit_type.name): unit_type for unit_type in stored}
        named = [by_name.get(normalize_unit_type_name(valid.name)) for valid in page]
        claimed = {unit_type.id for unit_type in named if unit_type is not None}

        result: list[UnitType] = []
        for valid, unit_type in zip(page, named, strict=True):
            if unit_type is not None:
                _log_area_change(unit_type, valid, url)
            else:
                free = [u for u in stored if u.id not in claimed]
                unit_type = self._by_area(valid, free, url) or self._new_unit_type(
                    project, valid, has_others=bool(stored), url=url, report=report
                )
                claimed.add(unit_type.id)
            result.append(unit_type)
        return result

    def _by_area(self, valid: ValidUnitType, free: list[UnitType], url: str) -> UnitType | None:
        candidates = unit_types_with_same_area(valid, free)
        if len(candidates) == 1:
            # Every match by area is logged so a wrong one can be found and undone.
            logger.info(
                "unit type %r at %s matched %r by area", valid.name, url, candidates[0].name
            )
            return candidates[0]
        if candidates:
            logger.warning(
                "unit type %r at %s has the area of %d unit types (%s): created a new one",
                valid.name,
                url,
                len(candidates),
                ", ".join(repr(u.name) for u in candidates),
            )
        return None

    def _new_unit_type(
        self,
        project: Project,
        valid: ValidUnitType,
        *,
        has_others: bool,
        url: str,
        report: ScrapeReport,
    ) -> UnitType:
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
        report.unit_types_added += 1
        if has_others:
            # A renamed unit type ("Tipo 4" for "Tipo 04") lands here; the log lets it be found.
            logger.info("new unit type %r at %s, in a project that had others", valid.name, url)
        return unit_type


def _log_area_change(unit_type: UnitType, valid: ValidUnitType, url: str) -> None:
    if (unit_type.built_area_m2, unit_type.private_area_m2) != (
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
