"""Read models for project listings: latest price and price per m² per unit type."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.pricing import ObservationSource


@dataclass(frozen=True)
class LatestPrice:
    """The most recent observed price of a unit type."""

    price_cop: int
    observed_on: date
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
    bedrooms: int
    bathrooms: int
    latest_price: LatestPrice | None

    @property
    def area_basis(self) -> AreaBasis:
        """PRIVATE when the private area is known, BUILT otherwise."""
        return AreaBasis.PRIVATE if self.private_area_m2 is not None else AreaBasis.BUILT

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
    location: GeoPoint
    source_url: str
    unit_types: list[UnitTypeListing]


@dataclass(frozen=True)
class ProjectPage:
    """One page of listings (ordered by project name); total ignores pagination."""

    items: list[ProjectListing]
    total: int
