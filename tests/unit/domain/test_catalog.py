from decimal import Decimal
from uuid import uuid4

import pytest

from sobreplano.domain.catalog import GeoPoint, UnitType
from sobreplano.domain.errors import DomainValidationError


def make_unit_type(
    private_area_m2: Decimal | None = Decimal("55.50"),
    built_area_m2: Decimal | None = None,
) -> UnitType:
    return UnitType(
        id=uuid4(),
        project_id=uuid4(),
        name="Tipo A",
        private_area_m2=private_area_m2,
        built_area_m2=built_area_m2,
        bedrooms=2,
        bathrooms=2,
    )


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(6.2442, -75.5812), (5.95, -75.80), (6.60, -75.20)],
)
def test_geo_point_accepts_aburra_valley(lat: float, lon: float) -> None:
    point = GeoPoint(lat=lat, lon=lon)
    assert (point.lat, point.lon) == (lat, lon)


@pytest.mark.parametrize(
    ("lat", "lon"),
    [
        (-75.5812, 6.2442),  # lat and lon swapped
        (5.94, -75.5),
        (6.61, -75.5),
        (6.2, -75.81),
        (6.2, -75.19),
        (float("nan"), -75.5),
    ],
)
def test_geo_point_rejects_outside_range(lat: float, lon: float) -> None:
    with pytest.raises(DomainValidationError):
        GeoPoint(lat=lat, lon=lon)


def test_unit_type_accepts_either_area() -> None:
    assert make_unit_type(private_area_m2=Decimal("40"), built_area_m2=None)
    assert make_unit_type(private_area_m2=None, built_area_m2=Decimal("48"))
    assert make_unit_type(private_area_m2=Decimal("40"), built_area_m2=Decimal("48"))


def test_unit_type_requires_at_least_one_area() -> None:
    with pytest.raises(DomainValidationError):
        make_unit_type(private_area_m2=None, built_area_m2=None)


@pytest.mark.parametrize("area", [Decimal("0"), Decimal("-1")])
def test_unit_type_rejects_non_positive_areas(area: Decimal) -> None:
    with pytest.raises(DomainValidationError):
        make_unit_type(private_area_m2=area)
    with pytest.raises(DomainValidationError):
        make_unit_type(private_area_m2=None, built_area_m2=area)
