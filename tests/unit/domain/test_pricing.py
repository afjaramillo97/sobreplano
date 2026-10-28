from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.pricing import ObservationSource, PriceObservation


def make_observation(
    price_cop: int = 320_000_000,
    observed_at: datetime | None = None,
) -> PriceObservation:
    return PriceObservation(
        id=uuid4(),
        unit_type_id=uuid4(),
        price_cop=price_cop,
        observed_at=observed_at or datetime(2026, 10, 28, 15, 0, tzinfo=UTC),
        observed_on=date(2026, 10, 28),
        source=ObservationSource.MANUAL,
        source_url="https://example.com/proyecto",
    )


def test_observation_accepts_positive_price_and_aware_datetime() -> None:
    assert make_observation().price_cop == 320_000_000


@pytest.mark.parametrize("price_cop", [0, -1])
def test_observation_rejects_non_positive_price(price_cop: int) -> None:
    with pytest.raises(DomainValidationError):
        make_observation(price_cop=price_cop)


def test_observation_requires_timezone() -> None:
    with pytest.raises(DomainValidationError):
        make_observation(observed_at=datetime(2026, 10, 28, 10, 0))
