"""Response models of the HTTP API, built from the domain read models."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.listings import (
    AreaBasis,
    LatestPrice,
    ProjectListing,
    ProjectPage,
    UnitTypeListing,
)
from sobreplano.domain.pricing import ObservationSource


class DeveloperOut(BaseModel):
    """Developer of a project."""

    name: str
    slug: str


class LocationOut(BaseModel):
    """WGS84 coordinates."""

    lat: float
    lon: float


class LatestPriceOut(BaseModel):
    """Most recent observed price of a unit type."""

    price_cop: int
    observed_on: date
    source: ObservationSource

    @classmethod
    def from_domain(cls, price: LatestPrice) -> "LatestPriceOut":
        return cls(price_cop=price.price_cop, observed_on=price.observed_on, source=price.source)


class UnitTypeOut(BaseModel):
    """A unit type with its latest price; areas are numbers, not strings."""

    id: UUID
    name: str
    private_area_m2: float | None
    built_area_m2: float | None
    bedrooms: int | None
    bathrooms: int | None
    latest_price: LatestPriceOut | None
    price_per_m2_cop: int | None
    area_basis: AreaBasis

    @classmethod
    def from_domain(cls, unit_type: UnitTypeListing) -> "UnitTypeOut":
        return cls(
            id=unit_type.id,
            name=unit_type.name,
            private_area_m2=_to_float(unit_type.private_area_m2),
            built_area_m2=_to_float(unit_type.built_area_m2),
            bedrooms=unit_type.bedrooms,
            bathrooms=unit_type.bathrooms,
            latest_price=(
                None
                if unit_type.latest_price is None
                else LatestPriceOut.from_domain(unit_type.latest_price)
            ),
            price_per_m2_cop=unit_type.price_per_m2_cop,
            area_basis=unit_type.area_basis,
        )


class ProjectOut(BaseModel):
    """A project with its developer and unit types."""

    id: UUID
    slug: str
    name: str
    developer: DeveloperOut
    municipality: Municipality
    neighborhood: str | None
    location: LocationOut
    source_url: str
    unit_types: list[UnitTypeOut]

    @classmethod
    def from_domain(cls, project: ProjectListing) -> "ProjectOut":
        return cls(
            id=project.id,
            slug=project.slug,
            name=project.name,
            developer=DeveloperOut(name=project.developer_name, slug=project.developer_slug),
            municipality=project.municipality,
            neighborhood=project.neighborhood,
            location=LocationOut(lat=project.location.lat, lon=project.location.lon),
            source_url=project.source_url,
            unit_types=[UnitTypeOut.from_domain(unit_type) for unit_type in project.unit_types],
        )


class ProjectListResponse(BaseModel):
    """One page of projects; total counts all matches, ignoring limit and offset."""

    items: list[ProjectOut]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_domain(cls, page: ProjectPage, *, limit: int, offset: int) -> "ProjectListResponse":
        return cls(
            items=[ProjectOut.from_domain(item) for item in page.items],
            total=page.total,
            limit=limit,
            offset=offset,
        )


def _to_float(value: Decimal | None) -> float | None:
    """Numeric(7, 2) areas as JSON numbers; Pydantic would serialize Decimal as text."""
    return None if value is None else float(value)
