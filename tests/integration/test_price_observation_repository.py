"""Integration tests for SqlPriceObservationRepository."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from sobreplano.application.record_price_observation import RecordPriceObservation, RecordResult
from sobreplano.domain.catalog import UnitType
from sobreplano.domain.errors import DuplicateObservationError
from sobreplano.domain.pricing import ObservationSource, PriceObservation
from sobreplano.infrastructure.db.price_observation_repository import (
    SqlPriceObservationRepository,
)

pytestmark = pytest.mark.integration


def make_observation(unit_type: UnitType, day: int, price_cop: int) -> PriceObservation:
    return PriceObservation(
        id=uuid4(),
        unit_type_id=unit_type.id,
        price_cop=price_cop,
        observed_at=datetime(2026, 10, day, 15, 0, tzinfo=UTC),
        observed_on=date(2026, 10, day),
        source=ObservationSource.MANUAL,
        source_url="https://example.com/proyecto",
    )


def test_observation_round_trip(
    observations: SqlPriceObservationRepository, unit_type: UnitType
) -> None:
    observation = make_observation(unit_type, 28, 320_000_000)
    observations.add(observation)
    assert observations.list_by_unit_type(unit_type.id) == [observation]


def test_observations_are_listed_oldest_first(
    observations: SqlPriceObservationRepository, unit_type: UnitType
) -> None:
    newer = make_observation(unit_type, 29, 330_000_000)
    older = make_observation(unit_type, 28, 320_000_000)
    observations.add(newer)
    observations.add(older)
    assert observations.list_by_unit_type(unit_type.id) == [older, newer]


def test_exists_for_day(observations: SqlPriceObservationRepository, unit_type: UnitType) -> None:
    observations.add(make_observation(unit_type, 28, 320_000_000))
    assert observations.exists_for_day(unit_type.id, date(2026, 10, 28))
    assert not observations.exists_for_day(unit_type.id, date(2026, 10, 29))
    assert not observations.exists_for_day(uuid4(), date(2026, 10, 28))


def test_second_insert_same_day_raises_duplicate_and_session_survives(
    observations: SqlPriceObservationRepository, unit_type: UnitType
) -> None:
    first = make_observation(unit_type, 28, 320_000_000)
    observations.add(first)
    with pytest.raises(DuplicateObservationError):
        observations.add(make_observation(unit_type, 28, 330_000_000))
    # The savepoint rolled back only the failed insert; the session can still query.
    assert observations.list_by_unit_type(unit_type.id) == [first]


class StaleCheckRepository(SqlPriceObservationRepository):
    """Simulates a concurrent run: its check does not yet see the other run's row."""

    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool:
        return False


def test_use_case_turns_a_race_into_already_recorded(session: Session, unit_type: UnitType) -> None:
    use_case = RecordPriceObservation(StaleCheckRepository(session))
    results = [
        use_case.execute(
            unit_type_id=unit_type.id,
            price_cop=price_cop,
            observed_at=datetime(2026, 10, 28, 15, 0, tzinfo=UTC),
            source=ObservationSource.SCRAPER,
            source_url="https://example.com/proyecto",
        )
        for price_cop in (320_000_000, 330_000_000)
    ]
    assert results == [RecordResult.RECORDED, RecordResult.ALREADY_RECORDED]
    prices = [
        o.price_cop for o in SqlPriceObservationRepository(session).list_by_unit_type(unit_type.id)
    ]
    assert prices == [320_000_000]
