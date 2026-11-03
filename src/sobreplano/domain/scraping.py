"""Scraping entities: runs, fetched pages, extraction results and the rules to accept them."""

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from sobreplano.domain.catalog import GeoPoint, Municipality

MIN_PRICE_COP = 50_000_000
MAX_PRICE_COP = 20_000_000_000
MIN_AREA_M2 = Decimal(15)
MAX_AREA_M2 = Decimal(1000)
MAX_ROOMS = 10


class ScrapeRunStatus(StrEnum):
    """Lifecycle of one scrape run of one developer."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    # Nothing done: another run held the lock, or one already succeeded today.
    SKIPPED = "skipped"


@dataclass(frozen=True)
class FetchedPage:
    """A page as the fetcher returned it; `url` is the final URL after redirects."""

    url: str
    status: int
    html: str
    fetched_at: datetime


@dataclass(frozen=True)
class ParsedProjectPage:
    """What the deterministic parser reads from an in-scope project page.

    Municipality, slug and location never come from the model, so lat and lon cannot be swapped.
    """

    canonical_url: str
    municipality: Municipality
    slug: str
    location: GeoPoint
    text: str  # clean text sent to the extractor


@dataclass(frozen=True)
class ScrapedPage:
    """A fetched page already stored in raw form; `url` is the canonical URL."""

    url: str
    http_status: int
    content_sha256: str  # hash of the raw HTML: names the stored file
    text_sha256: str  # hash of the clean text: the extraction reuse key
    storage_key: str
    fetched_at: datetime


@dataclass(frozen=True)
class ScrapeRun:
    """One pass over one developer's site on one day, with its counters."""

    id: UUID
    developer_id: UUID
    run_on: date
    started_at: datetime
    status: ScrapeRunStatus
    pages_fetched: int = 0
    pages_failed: int = 0
    observations_recorded: int = 0
    finished_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class ExtractedUnitType:
    """A unit type as the model read it from the page, before validation."""

    name: str
    price_cop: int | None
    total_area_m2: Decimal | None
    private_area_m2: Decimal | None
    bedrooms: int | None  # the minimum when the page gives a range ("2 o 3 alcobas")
    bathrooms: int | None


@dataclass(frozen=True)
class ExtractedProject:
    """A project as the model read it; municipality, slug and location come from the parser."""

    name: str
    neighborhood: str | None
    unit_types: tuple[ExtractedUnitType, ...]


@dataclass(frozen=True)
class ExtractionResult:
    """An extraction with the model that made it and its token usage (constitution, principle 5)."""

    model: str  # "provider:model", part of the reuse key
    input_tokens: int
    output_tokens: int
    project: ExtractedProject


@dataclass(frozen=True)
class ValidUnitType:
    """A unit type that passed the rules; `warnings` lists the fields that were dropped."""

    name: str
    price_cop: int
    built_area_m2: Decimal | None
    private_area_m2: Decimal | None
    bedrooms: int | None
    bathrooms: int | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RejectedUnitType:
    """A unit type that failed the rules; it is counted and logged, never stored."""

    name: str
    reason: str


def validate_unit_type(unit_type: ExtractedUnitType) -> ValidUnitType | RejectedUnitType:
    """Apply the range rules before anything reaches the append-only history.

    Rejects a unit type without a price in range or without at least one area in range.
    An area or room count out of range is dropped to None and reported in `warnings`.
    """
    # First line of defence against model mistakes and injected text: the history cannot be fixed.
    price = unit_type.price_cop
    if price is None:
        return RejectedUnitType(unit_type.name, "no price")
    if not MIN_PRICE_COP <= price <= MAX_PRICE_COP:
        return RejectedUnitType(unit_type.name, f"price {price} out of range")

    warnings: list[str] = []
    built = _area_in_range("total_area_m2", unit_type.total_area_m2, warnings)
    private = _area_in_range("private_area_m2", unit_type.private_area_m2, warnings)
    if built is None and private is None:
        return RejectedUnitType(unit_type.name, "no area in range")

    return ValidUnitType(
        name=unit_type.name,
        price_cop=price,
        built_area_m2=built,
        private_area_m2=private,
        bedrooms=_rooms_in_range("bedrooms", unit_type.bedrooms, warnings),
        bathrooms=_rooms_in_range("bathrooms", unit_type.bathrooms, warnings),
        warnings=tuple(warnings),
    )


def content_sha256(html: str) -> str:
    """Hex SHA-256 of the raw HTML's UTF-8 bytes: the name of the stored raw file."""
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def text_sha256(text: str) -> str:
    """Hex SHA-256 of the clean text's UTF-8 bytes: the extraction reuse key.

    The clean text is all the model sees, so the same text gives the same extraction even
    when the HTML around it changes (per-request form tokens change it every day).
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def raw_page_key(developer_slug: str, page: FetchedPage) -> str:
    """Storage key of a page's raw HTML: {developer}/{YYYY-MM-DD}/{sha256}.html.

    The day is the Bogotá date of fetched_at, the same day the price observation gets.
    Every RawPageStore uses this key, so disk and S3 stay interchangeable.
    """
    day = page.fetched_at.astimezone(ZoneInfo("America/Bogota")).date().isoformat()
    return f"{developer_slug}/{day}/{content_sha256(page.html)}.html"


def normalize_unit_type_name(name: str) -> str:
    """Key to match a unit type across days: NFKC, casefold, single spaces.

    "TIPO  B", "Tipo B" and "Tipo B " give the same key; NFKC also folds "m²" into "m2".
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name)).strip().casefold()


def dedupe_unit_types(valid: list[ValidUnitType]) -> list[ValidUnitType]:
    """Collapse unit types a page lists more than once, keeping the page order.

    Same normalized name and same areas is one unit type read twice (a summary and a
    card): it is kept once and, if the prices differ, with the lowest one, since sites
    publish "from" prices; the kept unit type gets a warning naming both prices. Same
    name with different areas are different unit types: each gets its area appended
    ("Tipo A · 55.58 m²"), so the stored names stay unique within the project.
    """
    kept: dict[tuple[str, Decimal | None, Decimal | None], ValidUnitType] = {}
    for unit in valid:
        key = (normalize_unit_type_name(unit.name), unit.built_area_m2, unit.private_area_m2)
        first = kept.get(key)
        if first is None:
            kept[key] = unit
        elif unit.price_cop != first.price_cop:
            low, high = sorted((first, unit), key=lambda u: u.price_cop)
            warning = f"listed twice, at {low.price_cop} and {high.price_cop}: kept the lowest"
            kept[key] = replace(low, warnings=(*low.warnings, warning))

    same_name = Counter(name for name, _, _ in kept)
    deduped = list(kept.values())
    for name, count in same_name.items():
        if count > 1:
            _append_areas(deduped, name)
    return deduped


def _append_areas(units: list[ValidUnitType], name: str) -> None:
    indexes = [i for i, u in enumerate(units) if normalize_unit_type_name(u.name) == name]
    labels = [_area_label(_main_area(units[i])) for i in indexes]
    # Same built area, different private area: one area is not enough to tell them apart.
    if len(set(labels)) < len(labels):
        labels = [
            f"{_area_label(units[i].built_area_m2)} / {_area_label(units[i].private_area_m2)}"
            for i in indexes
        ]
    for i, label in zip(indexes, labels, strict=True):
        units[i] = replace(units[i], name=f"{units[i].name} · {label}")


def _main_area(unit: ValidUnitType) -> Decimal | None:
    return unit.built_area_m2 if unit.built_area_m2 is not None else unit.private_area_m2


def _area_label(area: Decimal | None) -> str:
    # normalize() drops trailing zeros ("52.00" -> "52"); "f" avoids "1E+2" for 100.
    return "?" if area is None else f"{area.normalize():f} m²"


def _area_in_range(label: str, area: Decimal | None, warnings: list[str]) -> Decimal | None:
    if area is None:
        return None
    if not MIN_AREA_M2 <= area <= MAX_AREA_M2:
        warnings.append(f"{label} {area} out of range, dropped")
        return None
    return area


def _rooms_in_range(label: str, rooms: int | None, warnings: list[str]) -> int | None:
    if rooms is None:
        return None
    if not 0 <= rooms <= MAX_ROOMS:
        warnings.append(f"{label} {rooms} out of range, dropped")
        return None
    return rooms
