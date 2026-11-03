"""Unit tests for the rules of the listing read models: price per m², change and filters."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.listings import (
    AreaBasis,
    LatestPrice,
    PricePoint,
    ProjectFilters,
    UnitTypeListing,
)
from sobreplano.domain.pricing import ObservationSource


def make_unit_type(
    private_area_m2: str | None,
    built_area_m2: str | None,
    price_cop: int | None,
    first_price: PricePoint | None = None,
) -> UnitTypeListing:
    return UnitTypeListing(
        id=uuid4(),
        name="Tipo 02",
        private_area_m2=Decimal(private_area_m2) if private_area_m2 else None,
        built_area_m2=Decimal(built_area_m2) if built_area_m2 else None,
        bedrooms=1,
        bathrooms=2,
        latest_price=(
            LatestPrice(price_cop, date(2026, 10, 28), ObservationSource.MANUAL)
            if price_cop is not None
            else None
        ),
        first_price=first_price,
    )


def make_with_prices(
    first: int | None, latest: int | None, same_day: bool = False
) -> UnitTypeListing:
    """A unit type whose first price is on 28 Oct and whose latest is on 3 Nov (or 28 Oct)."""
    first_point = (
        PricePoint(date(2026, 10, 28), first, ObservationSource.MANUAL)
        if first is not None
        else None
    )
    unit_type = make_unit_type("54.98", None, latest, first_price=first_point)
    if latest is None or same_day:
        return unit_type
    return replace(
        unit_type,
        latest_price=LatestPrice(latest, date(2026, 11, 3), ObservationSource.SCRAPER),
    )


def test_price_per_m2_uses_private_area_when_present() -> None:
    unit_type = make_unit_type("54.98", "60.67", 716_500_000)
    assert unit_type.area_basis == AreaBasis.PRIVATE
    assert unit_type.price_per_m2_cop == round(716_500_000 / 54.98)


def test_price_per_m2_falls_back_to_built_area() -> None:
    unit_type = make_unit_type(None, "60.00", 600_000_000)
    assert unit_type.area_basis == AreaBasis.BUILT
    assert unit_type.price_per_m2_cop == 10_000_000


def test_price_per_m2_is_none_without_price() -> None:
    unit_type = make_unit_type("54.98", None, None)
    assert unit_type.latest_price is None
    assert unit_type.price_per_m2_cop is None


def test_price_per_m2_rounds_to_whole_pesos() -> None:
    # 100 / 3 = 33.33... rounds down; 200 / 3 = 66.66... rounds up.
    assert make_unit_type("3", None, 100).price_per_m2_cop == 33
    assert make_unit_type("3", None, 200).price_per_m2_cop == 67


def test_change_since_first_when_price_rises() -> None:
    assert make_with_prices(100_000_000, 110_000_000).change_since_first_pct == 10.0


def test_change_since_first_when_price_falls() -> None:
    assert make_with_prices(200_000_000, 190_000_000).change_since_first_pct == -5.0


def test_change_since_first_is_zero_when_price_is_equal() -> None:
    assert make_with_prices(716_500_000, 716_500_000).change_since_first_pct == 0.0


def test_change_since_first_rounds_to_one_decimal() -> None:
    # 1 / 3 % -> 0.333... -> 0.3
    assert make_with_prices(300_000_000, 301_000_000).change_since_first_pct == 0.3


def test_change_since_first_is_none_with_a_single_day() -> None:
    assert make_with_prices(100_000_000, 100_000_000, same_day=True).change_since_first_pct is None


def test_change_since_first_is_none_without_prices() -> None:
    assert make_with_prices(None, None).change_since_first_pct is None


def test_filters_default_to_no_filter() -> None:
    assert ProjectFilters() == ProjectFilters(developer=None, min_price=None)


def test_filters_accept_equal_minimum_and_maximum() -> None:
    ProjectFilters(min_price=5, max_price=5, min_area=Decimal("40"), max_area=Decimal("40"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_price": 900, "max_price": 100},
        {"min_area": Decimal("80"), "max_area": Decimal("40")},
        {"min_price": 0},
        {"max_price": -1},
        {"min_bedrooms": 0},
        {"min_area": Decimal("0")},
        {"max_area": Decimal("-5")},
    ],
)
def test_filters_reject_invalid_values(kwargs: dict[str, int | Decimal]) -> None:
    with pytest.raises(DomainValidationError):
        ProjectFilters(**kwargs)  # type: ignore[arg-type]
