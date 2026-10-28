from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.errors import DomainValidationError


class ObservationSource(StrEnum):
    MANUAL = "manual"
    SCRAPER = "scraper"


@dataclass(frozen=True)
class PriceObservation:
    id: UUID
    unit_type_id: UUID
    price_cop: int  # pesos enteros, > 0
    observed_at: datetime  # con zona horaria
    observed_on: date  # fecha de observed_at en America/Bogota
    source: ObservationSource
    source_url: str

    def __post_init__(self) -> None:
        if self.price_cop <= 0:
            raise DomainValidationError(f"price_cop must be > 0, got {self.price_cop}")
        if self.observed_at.tzinfo is None:
            raise DomainValidationError("observed_at must be timezone-aware")
