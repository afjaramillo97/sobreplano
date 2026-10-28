"""Price observation entity; observations are append-only (constitution, principle 2)."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sobreplano.domain.errors import DomainValidationError


class ObservationSource(StrEnum):
    """How a price was obtained."""

    MANUAL = "manual"
    SCRAPER = "scraper"


@dataclass(frozen=True)
class PriceObservation:
    """One price seen for a unit type at a point in time.

    price_cop is whole pesos. observed_on is the date of observed_at in America/Bogota,
    computed by the caller.

    Raises:
        DomainValidationError: if price_cop is not > 0 or observed_at has no timezone.
    """

    id: UUID
    unit_type_id: UUID
    price_cop: int
    observed_at: datetime
    observed_on: date
    source: ObservationSource
    source_url: str

    def __post_init__(self) -> None:
        if self.price_cop <= 0:
            raise DomainValidationError(f"price_cop must be > 0, got {self.price_cop}")
        if self.observed_at.tzinfo is None:
            raise DomainValidationError("observed_at must be timezone-aware")
