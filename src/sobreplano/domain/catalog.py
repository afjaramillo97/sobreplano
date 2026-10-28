"""Catalog entities: developers, projects and their unit types."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.errors import DomainValidationError


class Municipality(StrEnum):
    """Municipalities of the Aburrá Valley; values are the slugs stored in the database."""

    MEDELLIN = "medellin"
    BELLO = "bello"
    ITAGUI = "itagui"
    ENVIGADO = "envigado"
    SABANETA = "sabaneta"
    LA_ESTRELLA = "la_estrella"
    CALDAS = "caldas"
    COPACABANA = "copacabana"
    GIRARDOTA = "girardota"
    BARBOSA = "barbosa"


@dataclass(frozen=True)
class GeoPoint:
    """A WGS84 point inside the Aburrá Valley.

    Raises:
        DomainValidationError: if lat or lon fall outside the valley's bounding box.
    """

    lat: float
    lon: float

    def __post_init__(self) -> None:
        # The range check catches the classic mistake of swapping lat and lon.
        if not 5.95 <= self.lat <= 6.60:
            raise DomainValidationError(
                f"lat {self.lat} outside the Aburrá Valley (5.95 to 6.60); lat and lon swapped?"
            )
        if not -75.80 <= self.lon <= -75.20:
            raise DomainValidationError(
                f"lon {self.lon} outside the Aburrá Valley (-75.80 to -75.20); lat and lon swapped?"
            )


@dataclass(frozen=True)
class Developer:
    """A construction company that sells off-plan projects."""

    id: UUID
    name: str
    slug: str
    website_url: str


@dataclass(frozen=True)
class Project:
    """An off-plan housing project by one developer."""

    id: UUID
    developer_id: UUID
    name: str
    slug: str
    municipality: Municipality
    neighborhood: str | None
    location: GeoPoint
    source_url: str


@dataclass(frozen=True)
class UnitType:
    """A floor-plan type inside a project; prices are observed per unit type.

    Raises:
        DomainValidationError: if both areas are missing or any given area is not > 0.
    """

    id: UUID
    project_id: UUID
    name: str
    private_area_m2: Decimal | None
    built_area_m2: Decimal | None  # at least one of the two areas must be present
    bedrooms: int
    bathrooms: int

    def __post_init__(self) -> None:
        if self.private_area_m2 is None and self.built_area_m2 is None:
            raise DomainValidationError("a unit type needs private_area_m2 or built_area_m2")
        for label, area in (
            ("private_area_m2", self.private_area_m2),
            ("built_area_m2", self.built_area_m2),
        ):
            if area is not None and area <= 0:
                raise DomainValidationError(f"{label} must be > 0, got {area}")
