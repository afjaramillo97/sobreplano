"""validate_text must not reject the names and neighborhoods of real pages (SPEC 10)."""

from decimal import Decimal

import pytest

from sobreplano.domain.scraping import (
    MAX_NEIGHBORHOOD_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    MAX_UNIT_TYPE_NAME_LENGTH,
    ExtractedUnitType,
    screen_unit_types,
    validate_text,
)
from sobreplano.evals.extraction.golden import load_cache

pytestmark = pytest.mark.integration


def test_no_name_or_neighborhood_of_the_golden_set_is_rejected() -> None:
    labels, _ = load_cache()
    if not labels:
        pytest.skip("no golden set in .evals/: run `evals.extraction pull` first")
    rejected: list[str] = []
    for label in labels:
        checks = [(label.name, MAX_PROJECT_NAME_LENGTH)]
        if label.neighborhood is not None:
            checks.append((label.neighborhood, MAX_NEIGHBORHOOD_LENGTH))
        checks += [(unit.name, MAX_UNIT_TYPE_NAME_LENGTH) for unit in label.unit_types]
        rejected += [
            f"{label.case_id}: {text!r}"
            for text, limit in checks
            if validate_text(text, limit) is None
        ]
    assert rejected == []


def test_the_price_outlier_rule_rejects_no_real_unit_type_of_the_golden_set() -> None:
    """If this fails, the numbers (page, price per m², ratio) say which threshold to look at."""
    labels, _ = load_cache()
    if not labels:
        pytest.skip("no golden set in .evals/: run `evals.extraction pull` first")
    refused: list[str] = []
    for label in labels:
        extracted = [
            ExtractedUnitType(
                name=unit.name,
                price_cop=unit.price_cop,
                total_area_m2=None
                if unit.total_area_m2 is None
                else Decimal(str(unit.total_area_m2)),
                private_area_m2=(
                    None if unit.private_area_m2 is None else Decimal(str(unit.private_area_m2))
                ),
                bedrooms=unit.bedrooms,
                bathrooms=unit.bathrooms,
            )
            for unit in label.unit_types
        ]
        refused += [
            f"{label.case_id}: {r.name!r}: {r.reason}"
            for r in screen_unit_types(extracted).rejected
            if "outlier" in r.reason
        ]
    assert refused == []
