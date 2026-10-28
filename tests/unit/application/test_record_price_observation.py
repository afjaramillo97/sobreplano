"""Unit tests for the RecordPriceObservation use case, with an in-memory repository."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from sobreplano.application.record_price_observation import RecordPriceObservation, RecordResult
from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.pricing import ObservationSource, PriceObservation


class InMemoryPriceObservationRepository:
    def __init__(self) -> None:
        self.items: list[PriceObservation] = []

    def add(self, observation: PriceObservation) -> None:
        self.items.append(observation)

    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool:
        return any(
            o.unit_type_id == unit_type_id and o.observed_on == observed_on for o in self.items
        )

    def list_by_unit_type(self, unit_type_id: UUID) -> list[PriceObservation]:
        return [o for o in self.items if o.unit_type_id == unit_type_id]


def record(
    use_case: RecordPriceObservation,
    unit_type_id: UUID,
    observed_at: datetime,
    price_cop: int = 320_000_000,
) -> RecordResult:
    return use_case.execute(
        unit_type_id=unit_type_id,
        price_cop=price_cop,
        observed_at=observed_at,
        source=ObservationSource.MANUAL,
        source_url="https://example.com/proyecto",
    )


@pytest.fixture
def repo() -> InMemoryPriceObservationRepository:
    return InMemoryPriceObservationRepository()


@pytest.fixture
def use_case(repo: InMemoryPriceObservationRepository) -> RecordPriceObservation:
    return RecordPriceObservation(repo)


def test_records_a_new_observation(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    unit_type_id = uuid4()
    result = record(use_case, unit_type_id, datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    assert result is RecordResult.RECORDED
    assert [o.observed_on for o in repo.items] == [date(2026, 10, 28)]


def test_same_day_is_not_inserted_twice(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    unit_type_id = uuid4()
    record(use_case, unit_type_id, datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    result = record(
        use_case, unit_type_id, datetime(2026, 10, 28, 18, 0, tzinfo=UTC), price_cop=330_000_000
    )
    assert result is RecordResult.ALREADY_RECORDED
    assert len(repo.items) == 1
    assert repo.items[0].price_cop == 320_000_000


def test_other_unit_type_or_other_day_is_recorded(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    unit_type_id = uuid4()
    record(use_case, unit_type_id, datetime(2026, 10, 28, 15, 0, tzinfo=UTC))
    assert record(use_case, uuid4(), datetime(2026, 10, 28, 15, 0, tzinfo=UTC)) is (
        RecordResult.RECORDED
    )
    assert record(use_case, unit_type_id, datetime(2026, 10, 29, 15, 0, tzinfo=UTC)) is (
        RecordResult.RECORDED
    )
    assert len(repo.items) == 3


def test_observed_on_uses_bogota_day(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    unit_type_id = uuid4()
    # 03:00 UTC on the 29th is 22:00 on the 28th in Bogotá; 05:00 UTC is 00:00 on the 29th.
    record(use_case, unit_type_id, datetime(2026, 10, 29, 3, 0, tzinfo=UTC))
    record(use_case, unit_type_id, datetime(2026, 10, 29, 5, 0, tzinfo=UTC))
    assert [o.observed_on for o in repo.items] == [date(2026, 10, 28), date(2026, 10, 29)]


def test_naive_datetime_is_rejected(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    with pytest.raises(DomainValidationError):
        record(use_case, uuid4(), datetime(2026, 10, 28, 10, 0))
    assert repo.items == []


def test_invalid_price_is_rejected_and_nothing_is_added(
    use_case: RecordPriceObservation, repo: InMemoryPriceObservationRepository
) -> None:
    with pytest.raises(DomainValidationError):
        record(use_case, uuid4(), datetime(2026, 10, 28, 15, 0, tzinfo=UTC), price_cop=0)
    assert repo.items == []
