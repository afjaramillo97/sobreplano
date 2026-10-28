from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.errors import DomainValidationError


class Municipality(StrEnum):
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
    lat: float  # 5.95 <= lat <= 6.60: Valle de Aburrá
    lon: float  # -75.80 <= lon <= -75.20

    def __post_init__(self) -> None:
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
    id: UUID
    name: str
    slug: str
    website_url: str


@dataclass(frozen=True)
class Project:
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
    id: UUID
    project_id: UUID
    name: str
    private_area_m2: Decimal | None
    built_area_m2: Decimal | None  # al menos una
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
