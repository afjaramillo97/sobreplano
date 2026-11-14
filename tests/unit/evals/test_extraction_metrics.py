"""Unit tests for the extraction metrics over hand-made labels and outputs (no LLM)."""

from decimal import Decimal

import pytest

from sobreplano.domain.scraping import ExtractedProject, ExtractedUnitType
from sobreplano.evals.extraction.golden import ExpectedUnitType, ExtractionLabel
from sobreplano.evals.extraction.metrics import pair_unit_types, score_page, total


def expected(name: str, price: int | None = 400_000_000, **fields: object) -> ExpectedUnitType:
    values: dict[str, object] = {
        "total_area_m2": 60.0,
        "private_area_m2": 55.5,
        "bedrooms": 2,
        "bathrooms": 2,
    }
    values.update(fields)
    return ExpectedUnitType.model_validate({"name": name, "price_cop": price, **values})


def found(name: str, price: int | None = 400_000_000, **fields: object) -> ExtractedUnitType:
    values: dict[str, object] = {
        "total_area_m2": Decimal("60.0"),
        "private_area_m2": Decimal("55.5"),
        "bedrooms": 2,
        "bathrooms": 2,
    }
    values.update(fields)
    return ExtractedUnitType(name=name, price_cop=price, **values)  # type: ignore[arg-type]


def found_with(fields: dict[str, object]) -> ExtractedUnitType:
    values: dict[str, object] = {
        "total_area_m2": Decimal("60.0"),
        "private_area_m2": Decimal("55.5"),
        "bedrooms": 2,
        "bathrooms": 2,
        **fields,
    }
    return ExtractedUnitType(name="Tipo 1", price_cop=400_000_000, **values)  # type: ignore[arg-type]


def label(
    *units: ExpectedUnitType, name: str = "Réflex Living", hood: str | None = "Pan de Azúcar"
) -> ExtractionLabel:
    return ExtractionLabel(
        case_id="londono-gomez-reflex-living",
        url="https://example.com/reflex",
        developer="londono-gomez",
        text_sha256="a" * 64,
        reviewed=True,
        name=name,
        neighborhood=hood,
        unit_types=list(units),
    )


def project(
    *units: ExtractedUnitType, name: str = "RÉFLEX LIVING", hood: str | None = "Pan de Azucar"
) -> ExtractedProject:
    return ExtractedProject(name=name, neighborhood=hood, unit_types=units)


def test_identical_extraction_is_perfect() -> None:
    score = score_page(
        label(expected("Tipo 1"), expected("Tipo 2", None)),
        project(found("TIPO  1"), found("tipo 2", None)),
    )
    assert score.perfect
    assert (score.expected, score.found, score.matched, score.prices_ok, score.fields_ok) == (
        2,
        2,
        2,
        2,
        8,
    )
    assert score.problems == []


def test_missing_and_extra_unit_types_lower_recall_and_precision() -> None:
    score = score_page(
        label(expected("Tipo 1"), expected("Tipo 2")), project(found("Tipo 1"), found("Tipo 9"))
    )
    assert (score.expected, score.found, score.matched) == (2, 2, 1)
    assert "missing unit type 'Tipo 2'" in score.problems
    assert "extra unit type 'Tipo 9'" in score.problems
    metrics = total([score])
    assert (metrics.type_recall, metrics.type_precision) == (0.5, 0.5)


def test_repeated_names_pair_one_by_one_in_order() -> None:
    pairs, missing, extra = pair_unit_types(
        [expected("Tipo A", 300_000_000), expected("Tipo A", 310_000_000)],
        [found("Tipo A", 300_000_000), found("Tipo A", 310_000_000), found("Tipo A", 1)],
    )
    assert [(want.price_cop, got.price_cop) for want, got in pairs] == [
        (300_000_000, 300_000_000),
        (310_000_000, 310_000_000),
    ]
    assert (missing, extra) == ([], ["Tipo A"])


@pytest.mark.parametrize(
    ("got", "prices_ok"),
    [
        (found("Tipo 1", 400_000_000), 1),
        (found("Tipo 1", 400_000_001), 0),
        (found("Tipo 1", None), 0),
    ],
)
def test_price_must_be_exact(got: ExtractedUnitType, prices_ok: int) -> None:
    assert score_page(label(expected("Tipo 1")), project(got)).prices_ok == prices_ok


def test_null_price_matches_null() -> None:
    assert (
        score_page(
            label(expected("Planta típica", None)), project(found("Planta típica", None))
        ).prices_ok
        == 1
    )


@pytest.mark.parametrize(
    ("fields", "fields_ok"),
    [
        ({"private_area_m2": Decimal("55.55")}, 4),  # 0.05 m² off: inside the tolerance
        ({"private_area_m2": Decimal("55.56")}, 3),
        ({"total_area_m2": None}, 3),
        ({"bedrooms": 3}, 3),
        ({"bathrooms": None, "bedrooms": None}, 2),
    ],
)
def test_fields(fields: dict[str, object], fields_ok: int) -> None:
    assert score_page(label(expected("Tipo 1")), project(found_with(fields))).fields_ok == fields_ok


def test_project_name_and_neighborhood_ignore_accents_and_case() -> None:
    assert score_page(label(), project()).project_ok
    assert not score_page(label(), project(hood=None)).project_ok
    assert score_page(label(hood=None), project(hood=None)).project_ok


def test_failed_extraction_found_nothing() -> None:
    score = score_page(label(expected("Tipo 1")), None, "openai:gpt-6-luna: API error")
    assert (score.found, score.matched, score.project_ok, score.perfect) == (0, 0, False, False)
    assert total([score]).errors == 1


def test_totals_are_micro_averaged_and_check_eligibility() -> None:
    good = score_page(
        label(*[expected(f"Tipo {i}") for i in range(9)]),
        project(*[found(f"Tipo {i}") for i in range(9)]),
    )
    bad = score_page(label(expected("Tipo X")), project(found("Tipo X", 1)))
    metrics = total([good, bad])
    assert (metrics.pages, metrics.perfect_pages) == (2, 1)
    assert metrics.price_accuracy == pytest.approx(0.9)
    assert metrics.eligibility_failures() == ["price accuracy 90.0% < 98%"]
    assert total([good]).eligibility_failures() == []


def test_empty_label_and_empty_extraction_are_perfect() -> None:
    # A project with no unit types published, read as such.
    score = score_page(label(), project())
    assert score.perfect and total([score]).type_recall == 1.0
