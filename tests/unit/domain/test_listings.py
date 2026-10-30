"""Unit tests for the price per m² rule of UnitTypeListing."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sobreplano.domain.listings import AreaBasis, LatestPrice, UnitTypeListing
from sobreplano.domain.pricing import ObservationSource


def make_unit_type(
    private_area_m2: str | None,
    built_area_m2: str | None,
    price_cop: int | None,
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
