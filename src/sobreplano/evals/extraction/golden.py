"""Extraction golden set: labels, built from the cloud and S3, cached locally, never in git."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from sobreplano.domain.ports import DeveloperSite
from sobreplano.domain.scraping import FetchedPage, text_sha256
from sobreplano.infrastructure.db.models import (
    DeveloperRow,
    PageExtractionRow,
    ScrapedPageRow,
    ScrapeRunRow,
)
from sobreplano.infrastructure.scraping.extraction_schema import ExtractedProject

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

PAGES_PATH = Path("evals/extraction/pages.txt")
VERSION = "v1"
# Scraped data: kept in .evals/ (ignored by git) and in the raw bucket, never in the repo.
CACHE_DIR = Path(".evals/extraction") / VERSION
S3_PREFIX = f"evals/extraction/{VERSION}/"
LABELS_FILE = "labels.json"


class GoldenBuildError(Exception):
    """A page of pages.txt cannot become a golden case (not scraped, out of scope, changed)."""


class ExpectedUnitType(BaseModel):
    """A unit type as it really is on the page, checked by hand."""

    model_config = ConfigDict(extra="forbid")

    name: str
    price_cop: int | None
    total_area_m2: float | None
    private_area_m2: float | None
    bedrooms: int | None
    bathrooms: int | None


class ExtractionLabel(BaseModel):
    """The expected extraction of one page; `reviewed` only after reading the text by hand."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    url: str
    developer: str
    text_sha256: str
    reviewed: bool
    name: str
    neighborhood: str | None
    unit_types: list[ExpectedUnitType]


class LabelFile(BaseModel):
    """labels.json: every label of the golden set."""

    labels: list[ExtractionLabel]


def read_pages(path: Path = PAGES_PATH) -> list[str]:
    """URLs of pages.txt; blank lines and # comments are skipped."""
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def case_id(developer: str, url: str) -> str:
    """Readable, stable id: developer slug plus the last segment of the URL."""
    return f"{developer}-{url.rstrip('/').rsplit('/', 1)[-1]}"


def label_from_extraction(
    case: str, url: str, developer: str, sha: str, extraction: ExtractedProject
) -> ExtractionLabel:
    """A starting label from a stored extraction, not reviewed yet."""
    return ExtractionLabel(
        case_id=case,
        url=url,
        developer=developer,
        text_sha256=sha,
        reviewed=False,
        name=extraction.name,
        neighborhood=extraction.neighborhood,
        unit_types=[
            ExpectedUnitType(
                name=unit.name,
                price_cop=unit.price_cop,
                total_area_m2=unit.total_area_m2,
                private_area_m2=unit.private_area_m2,
                bedrooms=unit.bedrooms,
                bathrooms=unit.bathrooms,
            )
            for unit in extraction.unit_types
        ],
    )


def merge_labels(
    existing: Sequence[ExtractionLabel], built: Sequence[ExtractionLabel]
) -> list[ExtractionLabel]:
    """Built labels, except that a reviewed label of the same unchanged text is kept.

    So running build again never throws away a review, unless the page's text changed.
    """
    reviewed = {(label.case_id, label.text_sha256): label for label in existing if label.reviewed}
    return [reviewed.get((label.case_id, label.text_sha256), label) for label in built]


def build_case(
    session: Session,
    s3: "S3Client",
    bucket: str,
    sites: dict[str, Callable[[], DeveloperSite]],
    url: str,
) -> tuple[ExtractionLabel, str]:
    """Label and clean text of one URL, from its latest scraped page in the cloud.

    Raises:
        GoldenBuildError: if the URL was never scraped, its site is unknown, the page is out
            of scope, its clean text no longer has the stored hash, or it has no extraction.
    """
    row = session.execute(
        select(ScrapedPageRow, DeveloperRow.slug)
        .join(ScrapeRunRow, ScrapeRunRow.id == ScrapedPageRow.scrape_run_id)
        .join(DeveloperRow, DeveloperRow.id == ScrapeRunRow.developer_id)
        .where(ScrapedPageRow.url == url)
        .order_by(ScrapedPageRow.fetched_at.desc())
        .limit(1)
    ).one_or_none()
    if row is None:
        raise GoldenBuildError(f"{url}: never scraped")
    page, developer = row.tuple()
    if developer not in sites:
        raise GoldenBuildError(f"{url}: no site for developer {developer!r}")

    html = s3.get_object(Bucket=bucket, Key=page.storage_key)["Body"].read().decode("utf-8")
    fetched = FetchedPage(
        url=page.url, status=page.http_status, html=html, fetched_at=page.fetched_at
    )
    parsed = sites[developer]().parse_project(fetched)
    if parsed is None:
        raise GoldenBuildError(f"{url}: out of scope for its parser")
    sha = text_sha256(parsed.text)
    if page.text_sha256 is not None and sha != page.text_sha256:
        raise GoldenBuildError(f"{url}: the parser now gives another clean text than the scraper")

    payload = session.scalars(
        select(PageExtractionRow.payload)
        .where(PageExtractionRow.text_sha256 == sha)
        .order_by(PageExtractionRow.created_at.desc())
        .limit(1)
    ).one_or_none()
    if payload is None:
        raise GoldenBuildError(f"{url}: no stored extraction of its text")
    extraction = ExtractedProject.model_validate(payload)
    return label_from_extraction(
        case_id(developer, url), url, developer, sha, extraction
    ), parsed.text


def load_cache(cache: Path = CACHE_DIR) -> tuple[list[ExtractionLabel], dict[str, str]]:
    """Labels and texts (by case id) of the local cache; empty if there is none.

    Raises:
        FileNotFoundError: if a label's text file is missing.
    """
    path = cache / LABELS_FILE
    if not path.exists():
        return [], {}
    labels = LabelFile.model_validate_json(path.read_text(encoding="utf-8")).labels
    texts = {
        label.case_id: (cache / "texts" / f"{label.case_id}.txt").read_text(encoding="utf-8")
        for label in labels
    }
    return labels, texts


def save_cache(
    labels: Sequence[ExtractionLabel], texts: dict[str, str], cache: Path = CACHE_DIR
) -> None:
    """Write labels.json, pretty-printed for hand review, and one text file per case."""
    (cache / "texts").mkdir(parents=True, exist_ok=True)
    for case, text in texts.items():
        (cache / "texts" / f"{case}.txt").write_text(text, encoding="utf-8")
    (cache / LABELS_FILE).write_text(
        LabelFile(labels=list(labels)).model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def cache_files(cache: Path = CACHE_DIR) -> list[Path]:
    """Every file of the cache, relative to it."""
    return sorted(p.relative_to(cache) for p in cache.rglob("*") if p.is_file())


def push(s3: "S3Client", bucket: str, cache: Path = CACHE_DIR) -> int:
    """Upload the cache to s3://bucket/evals/extraction/v1/ and return the file count."""
    files = cache_files(cache)
    for relative in files:
        s3.put_object(
            Bucket=bucket,
            Key=S3_PREFIX + relative.as_posix(),
            Body=(cache / relative).read_bytes(),
            ContentType="application/json"
            if relative.suffix == ".json"
            else "text/plain; charset=utf-8",
        )
    return len(files)


def pull(s3: "S3Client", bucket: str, cache: Path = CACHE_DIR) -> int:
    """Download s3://bucket/evals/extraction/v1/ into the cache and return the file count."""
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=S3_PREFIX):
        for item in page.get("Contents", []):
            key = item.get("Key", "")
            target = cache / key.removeprefix(S3_PREFIX)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
            count += 1
    return count
