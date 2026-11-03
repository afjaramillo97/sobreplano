"""Read models for project listings: prices, price history and filters of the read API."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.pricing import ObservationSource


@dataclass(frozen=True)
class LatestPrice:
    """The most recent observed price of a unit type."""

    price_cop: int
    observed_on: date
    source: ObservationSource


@dataclass(frozen=True)
class PricePoint:
    """One observed price on one day, as shown in a unit type's history."""

    observed_on: date
    price_cop: int
    source: ObservationSource


class AreaBasis(StrEnum):
    """Which area a price per m² is computed on."""

    PRIVATE = "private"
    BUILT = "built"


@dataclass(frozen=True)
class UnitTypeListing:
    """A unit type with its latest price, or None if it has no observations."""

    id: UUID
    name: str
    private_area_m2: Decimal | None
    built_area_m2: Decimal | None
    bedrooms: int | None
    bathrooms: int | None
    latest_price: LatestPrice | None
    first_price: PricePoint | None  # first observation; None when there are no prices

    @property
    def area_basis(self) -> AreaBasis:
        """PRIVATE when the private area is known, BUILT otherwise."""
        return AreaBasis.PRIVATE if self.private_area_m2 is not None else AreaBasis.BUILT

    @property
    def change_since_first_pct(self) -> float | None:
        """Rise (or fall) from the first to the latest price, in percent with 1 decimal.

        None without prices, or when both are the same day: one observation says nothing
        about a change.
        """
        if self.latest_price is None or self.first_price is None:
            return None
        if self.latest_price.observed_on == self.first_price.observed_on:
            return None
        change = (
            self.latest_price.price_cop - self.first_price.price_cop
        ) / self.first_price.price_cop
        return round(change * 100, 1)

    @property
    def price_per_m2_cop(self) -> int | None:
        """Latest price divided by the base area, rounded to whole pesos; None without a price."""
        if self.latest_price is None:
            return None
        area = self.private_area_m2 if self.private_area_m2 is not None else self.built_area_m2
        # UnitType guarantees at least one area, but a read model built by hand might not.
        if area is None:
            return None
        return round(Decimal(self.latest_price.price_cop) / area)


@dataclass(frozen=True)
class ProjectListing:
    """A project with its developer and unit types (ordered by name)."""

    id: UUID
    slug: str
    name: str
    developer_name: str
    developer_slug: str
    municipality: Municipality
    neighborhood: str | None
    location: GeoPoint | None
    source_url: str
    unit_types: list[UnitTypeListing]


@dataclass(frozen=True)
class ProjectPage:
    """One page of listings (ordered by project name); total ignores pagination."""

    items: list[ProjectListing]
    total: int


@dataclass(frozen=True)
class UnitTypeDetail:
    """A unit type with its whole price history."""

    listing: UnitTypeListing
    history: list[PricePoint]  # oldest to newest


@dataclass(frozen=True)
class ProjectDetail:
    """A project (same fields as in the listing) with the history of each unit type."""

    project: ProjectListing
    unit_types: list[UnitTypeDetail]


@dataclass(frozen=True)
class DeveloperSummary:
    """A developer with the number of projects it has."""

    slug: str
    name: str
    website_url: str
    projects: int


class ProjectSort(StrEnum):
    """Order of a project listing."""

    NAME = "name"
    PRICE = "price"  # lowest latest price among the unit types that match the filters


@dataclass(frozen=True)
class ProjectFilters:
    """Filters of a project listing; None means no filter.

    Price and area apply to the latest price and the base area (private if known, else built)
    of a unit type; a project matches when one unit type meets all of them at once.

    Raises:
        DomainValidationError: if a number is not > 0 or a minimum is above its maximum.
    """

    municipality: Municipality | None = None
    developer: str | None = None  # slug
    min_price: int | None = None
    max_price: int | None = None
    min_bedrooms: int | None = None
    min_area: Decimal | None = None
    max_area: Decimal | None = None

    def __post_init__(self) -> None:
        numbers = {
            "min_price": self.min_price,
            "max_price": self.max_price,
            "min_bedrooms": self.min_bedrooms,
            "min_area": self.min_area,
            "max_area": self.max_area,
        }
        for name, value in numbers.items():
            if value is not None and value <= 0:
                raise DomainValidationError(f"{name} must be > 0, got {value}")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise DomainValidationError("min_price must be <= max_price")
        if (
            self.min_area is not None
            and self.max_area is not None
            and self.min_area > self.max_area
        ):
            raise DomainValidationError("min_area must be <= max_area")
