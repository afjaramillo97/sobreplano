"""Unit tests for the scraping range rules and unit type name matching."""

from decimal import Decimal

import pytest

from sobreplano.domain.scraping import (
    ExtractedUnitType,
    RejectedUnitType,
    ValidUnitType,
    normalize_unit_type_name,
    validate_unit_type,
)


def make_extracted(
    price_cop: int | None = 506_100_000,
    total_area_m2: Decimal | None = Decimal("55.58"),
    private_area_m2: Decimal | None = Decimal("49.36"),
    bedrooms: int | None = 2,
    bathrooms: int | None = 2,
) -> ExtractedUnitType:
    return ExtractedUnitType(
        name="TIPO B",
        price_cop=price_cop,
        total_area_m2=total_area_m2,
        private_area_m2=private_area_m2,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
    )


def test_valid_unit_type_maps_total_area_to_built_area() -> None:
    result = validate_unit_type(make_extracted())
    assert result == ValidUnitType(
        name="TIPO B",
        price_cop=506_100_000,
        built_area_m2=Decimal("55.58"),
        private_area_m2=Decimal("49.36"),
        bedrooms=2,
        bathrooms=2,
        warnings=(),
    )


@pytest.mark.parametrize("price_cop", [50_000_000, 20_000_000_000])
def test_price_bounds_are_inclusive(price_cop: int) -> None:
    assert isinstance(validate_unit_type(make_extracted(price_cop=price_cop)), ValidUnitType)


@pytest.mark.parametrize("price_cop", [None, 0, 49_999_999, 20_000_000_001, 506_100])
def test_rejects_missing_or_out_of_range_price(price_cop: int | None) -> None:
    result = validate_unit_type(make_extracted(price_cop=price_cop))
    assert isinstance(result, RejectedUnitType)


@pytest.mark.parametrize("area", [Decimal(15), Decimal(1000)])
def test_area_bounds_are_inclusive(area: Decimal) -> None:
    result = validate_unit_type(make_extracted(total_area_m2=area, private_area_m2=None))
    assert isinstance(result, ValidUnitType)
    assert result.built_area_m2 == area


def test_rejects_when_no_area_in_range() -> None:
    result = validate_unit_type(
        make_extracted(total_area_m2=Decimal("14.99"), private_area_m2=Decimal("1000.01"))
    )
    assert result == RejectedUnitType("TIPO B", "no area in range")


def test_rejects_when_no_area_at_all() -> None:
    result = validate_unit_type(make_extracted(total_area_m2=None, private_area_m2=None))
    assert isinstance(result, RejectedUnitType)


def test_drops_out_of_range_area_and_keeps_the_other() -> None:
    result = validate_unit_type(
        make_extracted(total_area_m2=Decimal(60), private_area_m2=Decimal(5))
    )
    assert isinstance(result, ValidUnitType)
    assert result.built_area_m2 == Decimal(60)
    assert result.private_area_m2 is None
    assert result.warnings == ("private_area_m2 5 out of range, dropped",)


@pytest.mark.parametrize("rooms", [0, 10])
def test_room_bounds_are_inclusive(rooms: int) -> None:
    result = validate_unit_type(make_extracted(bedrooms=rooms, bathrooms=rooms))
    assert isinstance(result, ValidUnitType)
    assert (result.bedrooms, result.bathrooms) == (rooms, rooms)


def test_keeps_missing_rooms_as_none_without_warning() -> None:
    result = validate_unit_type(make_extracted(bedrooms=None, bathrooms=None))
    assert isinstance(result, ValidUnitType)
    assert (result.bedrooms, result.bathrooms) == (None, None)
    assert result.warnings == ()


@pytest.mark.parametrize("rooms", [-1, 11, 23])
def test_drops_out_of_range_rooms_without_rejecting(rooms: int) -> None:
    result = validate_unit_type(make_extracted(bedrooms=rooms, bathrooms=rooms))
    assert isinstance(result, ValidUnitType)
    assert (result.bedrooms, result.bathrooms) == (None, None)
    assert len(result.warnings) == 2


@pytest.mark.parametrize(
    ("a", "b"),
    [("TIPO B", "Tipo B"), ("Tipo  1", "tipo 1"), (" Tipo A ", "tipo a")],
)
def test_normalized_names_match(a: str, b: str) -> None:
    assert normalize_unit_type_name(a) == normalize_unit_type_name(b)


def test_normalized_names_keep_distinct_types_apart() -> None:
    assert normalize_unit_type_name("Tipo 1") != normalize_unit_type_name("Tipo 11")
