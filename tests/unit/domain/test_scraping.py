"""Unit tests for the scraping range rules, unit type name matching and deduplication."""

from decimal import Decimal
from uuid import uuid4

import pytest

from sobreplano.domain.catalog import UnitType
from sobreplano.domain.scraping import (
    ExtractedUnitType,
    RejectedUnitType,
    ValidUnitType,
    dedupe_unit_types,
    normalize_unit_type_name,
    unit_types_with_same_area,
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
    [
        ("TIPO B", "Tipo B"),
        ("Tipo  1", "tipo 1"),
        (" Tipo A ", "tipo a"),
        ("Tipo B ", "TIPO B"),
        ("Tipo N\u0303", "TIPO \u00d1"),  # decomposed vs composed Ñ, joined by NFKC
        ("Planta 60.01 m²", "planta 60.01 m2"),
        ("Tipo Ñ", "tipo ñ"),
    ],
)
def test_normalized_names_match(a: str, b: str) -> None:
    assert normalize_unit_type_name(a) == normalize_unit_type_name(b)


def test_normalized_names_keep_distinct_types_apart() -> None:
    assert normalize_unit_type_name("Tipo 1") != normalize_unit_type_name("Tipo 11")


def valid(
    name: str = "Tipo A",
    price_cop: int = 260_000_000,
    built: str | None = "52",
    private: str | None = "47.1",
) -> ValidUnitType:
    return ValidUnitType(
        name=name,
        price_cop=price_cop,
        built_area_m2=None if built is None else Decimal(built),
        private_area_m2=None if private is None else Decimal(private),
        bedrooms=2,
        bathrooms=1,
        warnings=(),
    )


def test_dedupe_keeps_distinct_unit_types_as_they_are() -> None:
    units = [valid("Tipo A"), valid("Tipo B", built="60")]
    assert dedupe_unit_types(units) == units


def test_dedupe_keeps_one_of_an_exact_duplicate() -> None:
    # Seen on Verdeventura (2026-11-02): "Tipo A", same price and area, listed twice.
    units = [valid("Tipo A"), valid("Tipo B", built="60"), valid("TIPO A ")]
    assert dedupe_unit_types(units) == units[:2]


def test_dedupe_appends_the_area_to_same_name_with_different_areas() -> None:
    units = [valid("Tipo A", built="55.58"), valid("Tipo B"), valid("Tipo A", built="60.10")]
    assert [u.name for u in dedupe_unit_types(units)] == [
        "Tipo A · 55.58 m²",
        "Tipo B",
        "Tipo A · 60.1 m²",
    ]


def test_dedupe_uses_the_private_area_when_there_is_no_built_area() -> None:
    units = [valid(built=None, private="49.36"), valid(built=None, private="52.00")]
    assert [u.name for u in dedupe_unit_types(units)] == ["Tipo A · 49.36 m²", "Tipo A · 52 m²"]


def test_dedupe_uses_both_areas_when_the_built_area_is_shared() -> None:
    units = [valid(built="60", private="54.06"), valid(built="60", private="54.98")]
    assert [u.name for u in dedupe_unit_types(units)] == [
        "Tipo A · 60 m² / 54.06 m²",
        "Tipo A · 60 m² / 54.98 m²",
    ]


def test_dedupe_keeps_the_lowest_price_of_the_same_unit_type_and_warns() -> None:
    (kept,) = dedupe_unit_types([valid(price_cop=270_000_000), valid(price_cop=260_000_000)])
    assert kept.price_cop == 260_000_000
    assert kept.warnings == ("listed twice, at 260000000 and 270000000: kept the lowest",)


def stored(name: str, built: str | None, private: str | None) -> UnitType:
    return UnitType(
        id=uuid4(),
        project_id=uuid4(),
        name=name,
        private_area_m2=None if private is None else Decimal(private),
        built_area_m2=None if built is None else Decimal(built),
        bedrooms=1,
        bathrooms=1,
    )


def test_same_area_matches_built_or_private_to_two_decimals() -> None:
    tipo_04 = stored("Tipo 04", "60.01", "54.06")
    tipo_12 = stored("Tipo 12", "60.1", "54.94")
    tipo_02 = stored("Tipo 02", None, "54.98")
    candidates = [tipo_04, tipo_12, tipo_02]
    assert unit_types_with_same_area(valid(built="60.010", private="1"), candidates) == [tipo_04]
    assert unit_types_with_same_area(valid(built="60.10", private=None), candidates) == [tipo_12]
    assert unit_types_with_same_area(valid(built=None, private="54.98"), candidates) == [tipo_02]
    assert unit_types_with_same_area(valid(built="99", private="99"), candidates) == []
