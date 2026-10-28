from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.ports import PriceObservationRepository
from sobreplano.domain.pricing import ObservationSource, PriceObservation

BOGOTA = ZoneInfo("America/Bogota")


class RecordResult(StrEnum):
    RECORDED = "recorded"
    ALREADY_RECORDED = "already_recorded"


@dataclass(frozen=True)
class RecordPriceObservation:
    observations: PriceObservationRepository

    def execute(
        self,
        *,
        unit_type_id: UUID,
        price_cop: int,
        observed_at: datetime,
        source: ObservationSource,
        source_url: str,
    ) -> RecordResult:
        if observed_at.tzinfo is None:
            raise DomainValidationError("observed_at must be timezone-aware")
        observation = PriceObservation(
            id=uuid4(),
            unit_type_id=unit_type_id,
            price_cop=price_cop,
            observed_at=observed_at,
            observed_on=observed_at.astimezone(BOGOTA).date(),
            source=source,
            source_url=source_url,
        )
        if self.observations.exists_for_day(unit_type_id, observation.observed_on):
            return RecordResult.ALREADY_RECORDED
        self.observations.add(observation)
        return RecordResult.RECORDED
