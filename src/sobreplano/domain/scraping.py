"""Scraping entities: runs, fetched pages, extraction results and the rules to accept them."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

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
    content_sha256: str
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


def normalize_unit_type_name(name: str) -> str:
    """Key to match a unit type across days: lowercase, single spaces ("TIPO  B" == "Tipo B")."""
    return re.sub(r"\s+", " ", name).strip().lower()


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
