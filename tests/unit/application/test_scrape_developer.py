"""Unit tests for ScrapeDeveloper, with in-memory fakes of every port."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from sobreplano.application.record_price_observation import RecordPriceObservation
from sobreplano.application.scrape_developer import ScrapeDeveloper
from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType
from sobreplano.domain.errors import ExtractionError, FetchError, PageParseError
from sobreplano.domain.pricing import PriceObservation
from sobreplano.domain.scraping import (
    ExtractedProject,
    ExtractedUnitType,
    ExtractionResult,
    FetchedPage,
    ParsedProjectPage,
    ScrapedPage,
    ScrapeRun,
    ScrapeRunStatus,
)

LISTING = "https://example.com/proyectos"
NOW = datetime(2026, 10, 30, 15, 0, tzinfo=UTC)
MODEL = "openai:gpt-6-luna"


def unit(
    name: str = "Tipo 1",
    price_cop: int | None = 426_706_000,
    total: str | None = "55",
    private: str | None = "49.36",
    bedrooms: int | None = 2,
) -> ExtractedUnitType:
    return ExtractedUnitType(
        name=name,
        price_cop=price_cop,
        total_area_m2=None if total is None else Decimal(total),
        private_area_m2=None if private is None else Decimal(private),
        bedrooms=bedrooms,
        bathrooms=2,
    )


def project(name: str, *units: ExtractedUnitType) -> ExtractedProject:
    return ExtractedProject(name=name, neighborhood="Pan de Azúcar", unit_types=units)


class FakeSite:
    """Listing HTML is the node URLs, one per line; pages map to parse results."""

    slug = "londono-gomez"
    name = "Londoño Gómez"
    website_url = "https://example.com"
    listing_url = LISTING

    def __init__(self) -> None:
        self.pages: dict[str, ParsedProjectPage | Exception | None] = {}

    def add(self, node: str, slug: str, municipality: Municipality = Municipality.BELLO) -> str:
        self.pages[node] = ParsedProjectPage(
            canonical_url=f"https://example.com/proyectos-vivienda/antioquia/x/{slug}",
            municipality=municipality,
            slug=slug,
            location=GeoPoint(lat=6.3296, lon=-75.5596),
            text=f"texto de {slug}",
        )
        return node

    def project_urls(self, listing_html: str) -> list[str]:
        return listing_html.split()

    def parse_project(self, page: FetchedPage) -> ParsedProjectPage | None:
        result = self.pages[page.url]
        if isinstance(result, Exception):
            raise result
        return result


class FakeFetcher:
    def __init__(self, site: FakeSite) -> None:
        self.site = site
        self.errors: dict[str, Exception] = {}
        self.status: dict[str, int] = {}
        self.requested: list[str] = []
        self.fetched_at = NOW

    def fetch(self, url: str) -> FetchedPage:
        self.requested.append(url)
        if url in self.errors:
            raise self.errors[url]
        html = "\n".join(self.site.pages) if url == LISTING else f"<html>{url}</html>"
        return FetchedPage(
            url=url, status=self.status.get(url, 200), html=html, fetched_at=self.fetched_at
        )


class FakeStore:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save(self, developer_slug: str, page: FetchedPage) -> str:
        self.saved.append(page.url)
        return f"{developer_slug}/{page.url}"


class FakeExtractor:
    model = MODEL

    def __init__(self) -> None:
        self.projects: dict[str, ExtractedProject | Exception] = {}
        self.calls: list[str] = []

    def extract(self, page_text: str) -> ExtractionResult:
        self.calls.append(page_text)
        result = self.projects[page_text]
        if isinstance(result, Exception):
            raise result
        return ExtractionResult(model=MODEL, input_tokens=1000, output_tokens=100, project=result)


@dataclass
class FakeRuns:
    started: list[ScrapeRun] = field(default_factory=list[ScrapeRun])
    pages: list[tuple[UUID, ScrapedPage]] = field(default_factory=list[tuple[UUID, ScrapedPage]])
    extractions: dict[tuple[str, str], ExtractionResult] = field(
        default_factory=dict[tuple[str, str], ExtractionResult]
    )
    finished: list[ScrapeRun] = field(default_factory=list[ScrapeRun])

    def start(self, developer_id: UUID, run_on: date) -> ScrapeRun:
        run = ScrapeRun(
            id=uuid4(),
            developer_id=developer_id,
            run_on=run_on,
            started_at=NOW,
            status=ScrapeRunStatus.RUNNING,
        )
        self.started.append(run)
        return run

    def record_page(self, run_id: UUID, page: ScrapedPage) -> None:
        self.pages.append((run_id, page))

    def find_extraction(self, content_sha256: str, model: str) -> ExtractionResult | None:
        return self.extractions.get((content_sha256, model))

    def save_extraction(self, content_sha256: str, result: ExtractionResult) -> None:
        self.extractions[(content_sha256, result.model)] = result

    def finish(self, run: ScrapeRun) -> None:
        self.finished.append(run)


class InMemoryCatalog:
    def __init__(self) -> None:
        self.developers: list[Developer] = []
        self.projects: list[Project] = []
        self.unit_types: list[UnitType] = []

    def add_developer(self, developer: Developer) -> None:
        self.developers.append(developer)

    def get_developer_by_slug(self, slug: str) -> Developer | None:
        return next((d for d in self.developers if d.slug == slug), None)

    def add_project(self, project: Project) -> None:
        self.projects.append(project)

    def get_project_by_slug(self, slug: str) -> Project | None:
        return next((p for p in self.projects if p.slug == slug), None)

    def add_unit_type(self, unit_type: UnitType) -> None:
        self.unit_types.append(unit_type)

    def list_unit_types(self, project_id: UUID) -> list[UnitType]:
        return [u for u in self.unit_types if u.project_id == project_id]


class InMemoryObservations:
    def __init__(self) -> None:
        self.items: list[PriceObservation] = []

    def add(self, observation: PriceObservation) -> None:
        self.items.append(observation)

    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool:
        return any(
            o.unit_type_id == unit_type_id and o.observed_on == observed_on for o in self.items
        )

    def list_by_unit_type(self, unit_type_id: UUID) -> list[PriceObservation]:
        return [o for o in self.items if o.unit_type_id == unit_type_id]


@dataclass
class World:
    site: FakeSite = field(default_factory=FakeSite)
    store: FakeStore = field(default_factory=FakeStore)
    extractor: FakeExtractor = field(default_factory=FakeExtractor)
    runs: FakeRuns = field(default_factory=FakeRuns)
    catalog: InMemoryCatalog = field(default_factory=InMemoryCatalog)
    observations: InMemoryObservations = field(default_factory=InMemoryObservations)

    def __post_init__(self) -> None:
        self.fetcher = FakeFetcher(self.site)

    def page(self, node: str, slug: str, extracted: ExtractedProject | Exception) -> str:
        self.site.add(node, slug)
        self.extractor.projects[f"texto de {slug}"] = extracted
        return node

    def use_case(self) -> ScrapeDeveloper:
        return ScrapeDeveloper(
            site=self.site,
            fetcher=self.fetcher,
            store=self.store,
            extractor=self.extractor,
            runs=self.runs,
            catalog=self.catalog,
            record=RecordPriceObservation(self.observations),
            now=lambda: NOW,
        )


@pytest.fixture
def world() -> World:
    world = World()
    world.page("/node/1", "primavela", project("Primavela", unit("TIPO B"), unit("TIPO D")))
    world.page("/node/2", "reflex-living", project("Réflex Living", unit("Tipo 1")))
    return world


def test_full_run_creates_catalog_and_records_one_price_per_unit_type(world: World) -> None:
    report = world.use_case().execute()

    assert report.status is ScrapeRunStatus.SUCCEEDED
    assert (report.pages_listed, report.pages_fetched, report.pages_failed) == (2, 2, 0)
    assert [d.slug for d in world.catalog.developers] == ["londono-gomez"]
    assert [p.slug for p in world.catalog.projects] == ["primavela", "reflex-living"]
    assert [p.neighborhood for p in world.catalog.projects] == ["Pan de Azúcar"] * 2
    assert len(world.catalog.unit_types) == 3
    assert report.observations_recorded == 3
    assert [o.price_cop for o in world.observations.items] == [426_706_000] * 3
    assert (report.input_tokens, report.output_tokens) == (2000, 200)


def test_location_and_municipality_come_from_the_parser(world: World) -> None:
    world.use_case().execute()
    primavela = world.catalog.projects[0]
    assert primavela.location == GeoPoint(lat=6.3296, lon=-75.5596)
    assert primavela.municipality is Municipality.BELLO
    assert primavela.source_url.endswith("/primavela")


def test_pages_are_stored_with_their_canonical_url(world: World) -> None:
    world.use_case().execute()
    run_id = world.runs.started[0].id
    assert [(page_run_id, page.url) for page_run_id, page in world.runs.pages] == [
        (run_id, "https://example.com/proyectos-vivienda/antioquia/x/primavela"),
        (run_id, "https://example.com/proyectos-vivienda/antioquia/x/reflex-living"),
    ]
    assert world.store.saved == ["/node/1", "/node/2"]


def test_run_is_finished_with_its_counters(world: World) -> None:
    world.use_case().execute()
    (finished,) = world.runs.finished
    assert finished.status is ScrapeRunStatus.SUCCEEDED
    assert (finished.pages_fetched, finished.pages_failed, finished.observations_recorded) == (
        2,
        0,
        3,
    )
    assert finished.finished_at == NOW
    assert finished.error is None
    assert finished.run_on == date(2026, 10, 30)


def test_second_run_same_day_reuses_extractions_and_records_nothing(world: World) -> None:
    world.use_case().execute()
    world.extractor.calls.clear()

    report = world.use_case().execute()

    assert world.extractor.calls == []
    assert (report.input_tokens, report.output_tokens) == (0, 0)
    assert report.extractions_reused == 2
    assert report.observations_recorded == 0
    assert report.observations_already_recorded == 3
    assert report.status is ScrapeRunStatus.SUCCEEDED
    assert len(world.catalog.unit_types) == 3
    assert len(world.catalog.developers) == 1


def test_out_of_scope_page_is_not_stored_extracted_or_recorded(world: World) -> None:
    world.site.pages["/node/3"] = None
    report = world.use_case().execute()
    assert report.pages_out_of_scope == 1
    assert "/node/3" in world.fetcher.requested
    assert "/node/3" not in world.store.saved
    assert len(world.runs.pages) == 2
    assert report.pages_failed == 0


def test_second_node_with_the_same_canonical_page_is_skipped(world: World) -> None:
    world.site.pages["/node/9"] = world.site.pages["/node/1"]
    report = world.use_case().execute()
    assert report.pages_out_of_scope == 1
    assert len(world.runs.pages) == 2


@pytest.mark.parametrize(
    "error",
    [
        FetchError("timed out"),
        PageParseError("no canonical link"),
        ExtractionError("refused"),
    ],
)
def test_failing_page_is_counted_and_the_run_goes_on(world: World, error: Exception) -> None:
    if isinstance(error, FetchError):
        world.fetcher.errors["/node/1"] = error
    elif isinstance(error, PageParseError):
        world.site.pages["/node/1"] = error
    else:
        world.extractor.projects["texto de primavela"] = error

    report = world.use_case().execute()

    assert report.pages_failed == 1
    assert report.failures == [f"/node/1: {error}"]
    assert report.observations_recorded == 1
    assert report.status is ScrapeRunStatus.SUCCEEDED


def test_non_200_page_is_a_failure(world: World) -> None:
    world.fetcher.status["/node/1"] = 404
    report = world.use_case().execute()
    assert report.pages_failed == 1
    assert world.store.saved == ["/node/2"]


def test_run_fails_when_no_page_records_a_price(world: World) -> None:
    world.extractor.projects["texto de primavela"] = ExtractionError("refused")
    world.extractor.projects["texto de reflex-living"] = project("Réflex", unit(price_cop=None))
    report = world.use_case().execute()
    assert report.status is ScrapeRunStatus.FAILED
    assert world.runs.finished[0].error == "no page recorded a price (1 failed)"


def test_run_fails_when_the_listing_cannot_be_fetched(world: World) -> None:
    world.fetcher.errors[LISTING] = FetchError("robots.txt disallows")
    report = world.use_case().execute()
    assert report.status is ScrapeRunStatus.FAILED
    assert world.fetcher.requested == [LISTING]
    assert world.runs.finished[0].error == "robots.txt disallows"


def test_limit_caps_the_pages(world: World) -> None:
    report = world.use_case().execute(limit=1)
    assert report.pages_listed == 1
    assert world.fetcher.requested == [LISTING, "/node/1"]


def test_rejected_unit_types_are_counted_not_stored(world: World) -> None:
    world.extractor.projects["texto de primavela"] = project(
        "Primavela",
        unit("TIPO B"),
        unit("PLANTA TÍPICA", price_cop=None),
        unit("Tipo raro", price_cop=1),
        unit("Sin área", total=None, private=None),
    )
    report = world.use_case().execute()
    assert report.unit_types_rejected == 3
    names = {u.name for u in world.catalog.unit_types}
    assert names == {"TIPO B", "Tipo 1"}


def test_unit_type_name_matches_across_case_and_spaces(world: World) -> None:
    world.use_case().execute()
    # The next day the page writes "Tipo  b" for "TIPO B" (and new HTML, so a new extraction).
    world.extractor.projects["texto de primavela"] = project("Primavela", unit("Tipo  b"))
    world.runs.extractions.clear()
    world.fetcher.fetched_at = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)

    report = world.use_case().execute()

    assert report.unit_types_added == 0
    assert report.observations_recorded == 2


def test_missing_bedrooms_are_stored_as_none(world: World) -> None:
    world.extractor.projects["texto de reflex-living"] = project(
        "Réflex Living", unit("Tipo 1", bedrooms=None)
    )
    world.use_case().execute()
    reflex = next(u for u in world.catalog.unit_types if u.name == "Tipo 1")
    assert reflex.bedrooms is None


def test_project_slug_of_another_developer_is_a_failure(world: World) -> None:
    other = uuid4()
    world.catalog.projects.append(
        Project(
            id=uuid4(),
            developer_id=other,
            name="Primavela",
            slug="primavela",
            municipality=Municipality.BELLO,
            neighborhood=None,
            location=GeoPoint(lat=6.3, lon=-75.55),
            source_url="https://other.example.com",
        )
    )
    report = world.use_case().execute()
    assert report.pages_failed == 1
    assert "another developer" in report.failures[0]
