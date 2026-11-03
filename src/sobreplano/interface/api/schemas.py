"""Response models of the HTTP API, built from the domain read models."""

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.listings import (
    AreaBasis,
    DeveloperSummary,
    LatestPrice,
    PricePoint,
    ProjectDetail,
    ProjectListing,
    ProjectPage,
    UnitTypeDetail,
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


class PricePointOut(BaseModel):
    """One observed price on one day: the first price of a unit type or a history entry."""

    price_cop: int
    observed_on: date
    source: ObservationSource

    @classmethod
    def from_domain(cls, point: PricePoint) -> "PricePointOut":
        return cls(price_cop=point.price_cop, observed_on=point.observed_on, source=point.source)


class UnitTypeOut(BaseModel):
    """A unit type with its latest and first price; areas are numbers, not strings."""

    id: UUID
    name: str
    private_area_m2: float | None
    built_area_m2: float | None
    bedrooms: int | None
    bathrooms: int | None
    latest_price: LatestPriceOut | None
    first_price: PricePointOut | None
    change_since_first_pct: float | None  # null without prices or with a single day of them
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
            first_price=(
                None
                if unit_type.first_price is None
                else PricePointOut.from_domain(unit_type.first_price)
            ),
            change_since_first_pct=unit_type.change_since_first_pct,
            price_per_m2_cop=unit_type.price_per_m2_cop,
            area_basis=unit_type.area_basis,
        )


class UnitTypeDetailOut(UnitTypeOut):
    """A unit type with its whole price history, oldest first."""

    history: list[PricePointOut]

    @classmethod
    def from_detail(cls, detail: UnitTypeDetail) -> "UnitTypeDetailOut":
        return cls(
            **UnitTypeOut.from_domain(detail.listing).model_dump(),
            history=[PricePointOut.from_domain(point) for point in detail.history],
        )


class ProjectBase(BaseModel):
    """Fields shared by the listing and the detail of a project."""

    id: UUID
    slug: str
    name: str
    developer: DeveloperOut
    municipality: Municipality
    neighborhood: str | None
    location: LocationOut | None  # null while the developer publishes no map
    source_url: str


class ProjectOut(ProjectBase):
    """A project in the listing. With unit type filters, only the unit types that match."""

    unit_types: list[UnitTypeOut]

    @classmethod
    def from_domain(cls, project: ProjectListing) -> "ProjectOut":
        return cls(
            **_project_fields(project),
            unit_types=[UnitTypeOut.from_domain(unit_type) for unit_type in project.unit_types],
        )


class ProjectDetailOut(ProjectBase):
    """A project with all its unit types and their price history."""

    unit_types: list[UnitTypeDetailOut]

    @classmethod
    def from_domain(cls, detail: ProjectDetail) -> "ProjectDetailOut":
        return cls(
            **_project_fields(detail.project),
            unit_types=[UnitTypeDetailOut.from_detail(unit) for unit in detail.unit_types],
        )


class DeveloperSummaryOut(BaseModel):
    """A developer with its number of projects."""

    slug: str
    name: str
    website_url: str
    projects: int

    @classmethod
    def from_domain(cls, summary: DeveloperSummary) -> "DeveloperSummaryOut":
        return cls(
            slug=summary.slug,
            name=summary.name,
            website_url=summary.website_url,
            projects=summary.projects,
        )


def _project_fields(project: ProjectListing) -> dict[str, Any]:
    """The fields of ProjectBase, read from a listing."""
    return {
        "id": project.id,
        "slug": project.slug,
        "name": project.name,
        "developer": DeveloperOut(name=project.developer_name, slug=project.developer_slug),
        "municipality": project.municipality,
        "neighborhood": project.neighborhood,
        "location": (
            None
            if project.location is None
            else LocationOut(lat=project.location.lat, lon=project.location.lon)
        ),
        "source_url": project.source_url,
    }


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
