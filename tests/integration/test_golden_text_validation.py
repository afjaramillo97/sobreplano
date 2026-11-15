"""validate_text must not reject the names and neighborhoods of real pages (SPEC 10)."""

import pytest

from sobreplano.domain.scraping import (
    MAX_NEIGHBORHOOD_LENGTH,
    MAX_PROJECT_NAME_LENGTH,
    MAX_UNIT_TYPE_NAME_LENGTH,
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
