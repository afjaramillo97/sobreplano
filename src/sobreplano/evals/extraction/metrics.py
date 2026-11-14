"""Extraction metrics: unit types paired by name, then by area, then compared field by field."""

from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel

from sobreplano.domain.scraping import ExtractedProject, ExtractedUnitType, normalize_unit_type_name
from sobreplano.evals.advisor.checks import normalize
from sobreplano.evals.extraction.golden import ExpectedUnitType, ExtractionLabel

AREA_TOLERANCE = Decimal("0.05")  # m²
FIELDS_PER_UNIT_TYPE = 4  # total area, private area, bedrooms, bathrooms

# A model is eligible as the extractor only if it meets all three (SPEC 09).
MIN_PRICE_ACCURACY = 0.98
MIN_TYPE_RECALL = 0.95
MIN_FIELD_ACCURACY = 0.95


class PageScore(BaseModel):
    """How one extraction compares with its label."""

    case_id: str
    expected: int  # unit types in the label
    found: int  # unit types the model returned
    matched: int
    names_exact: int = 0  # matched unit types whose name is the label's, normalized
    prices_ok: int
    fields_ok: int
    project_ok: bool
    problems: list[str]
    pairing: dict[str, str] = {}  # label unit type name -> name the model gave it
    error: str | None = None  # the extraction failed: nothing was found

    @property
    def perfect(self) -> bool:
        """No error, no missing or extra unit type, every price, field and project field right."""
        return (
            self.error is None
            and self.matched == self.expected == self.found
            and self.prices_ok == self.matched
            and self.fields_ok == self.matched * FIELDS_PER_UNIT_TYPE
            and self.project_ok
        )


class Metrics(BaseModel):
    """Totals over many pages (micro-averaged: each unit type and field counts once)."""

    pages: int
    expected: int
    found: int
    matched: int
    names_exact: int = 0
    prices_ok: int
    fields_ok: int
    projects_ok: int
    perfect_pages: int
    errors: int

    @property
    def type_recall(self) -> float:
        """Expected unit types the model found."""
        return self.matched / self.expected if self.expected else 1.0

    @property
    def type_precision(self) -> float:
        """Unit types the model found that exist in the label."""
        return self.matched / self.found if self.found else 1.0

    @property
    def name_accuracy(self) -> float:
        """Matched unit types named exactly as in the label (report only, no threshold)."""
        return self.names_exact / self.matched if self.matched else 1.0

    @property
    def price_accuracy(self) -> float:
        """Matched unit types whose price is right (null with null counts as right)."""
        return self.prices_ok / self.matched if self.matched else 1.0

    @property
    def field_accuracy(self) -> float:
        """Matched fields that are right: areas within 0.05 m², bedrooms and bathrooms equal."""
        total = self.matched * FIELDS_PER_UNIT_TYPE
        return self.fields_ok / total if total else 1.0

    @property
    def project_accuracy(self) -> float:
        """Pages whose project name and neighborhood are right."""
        return self.projects_ok / self.pages if self.pages else 1.0

    def eligibility_failures(self) -> list[str]:
        """Thresholds this model misses as the extractor; empty means eligible."""
        checks = [
            ("price accuracy", self.price_accuracy, MIN_PRICE_ACCURACY),
            ("unit type recall", self.type_recall, MIN_TYPE_RECALL),
            ("field accuracy", self.field_accuracy, MIN_FIELD_ACCURACY),
        ]
        return [
            f"{name} {value:.1%} < {minimum:.0%}"
            for name, value, minimum in checks
            if value < minimum
        ]


def pair_unit_types(
    expected: Sequence[ExpectedUnitType], found: Sequence[ExtractedUnitType]
) -> tuple[list[tuple[ExpectedUnitType, ExtractedUnitType]], list[str], list[str]]:
    """Pairs by normalized name first, then by area; repeated names pair one by one.

    What is left pairs by area (total or private, within AREA_TOLERANCE) only when the area
    is unambiguous: one leftover label unit and one leftover found unit share it. Models
    drop or add words such as "Planta" or "Área Total"; the area still says which unit type it
    is. Two leftovers with the same area are a tie, and a tie pairs nothing.

    Returns the pairs, the expected names left unpaired and the found names left unpaired.
    """
    available: dict[str, list[ExtractedUnitType]] = {}
    for unit in found:
        available.setdefault(normalize_unit_type_name(unit.name), []).append(unit)
    pairs: list[tuple[ExpectedUnitType, ExtractedUnitType]] = []
    unpaired: list[ExpectedUnitType] = []
    for unit in expected:
        candidates = available.get(normalize_unit_type_name(unit.name), [])
        if candidates:
            pairs.append((unit, candidates.pop(0)))
        else:
            unpaired.append(unit)

    leftovers = [unit for units in available.values() for unit in units]
    missing: list[str] = []
    for want in unpaired:
        same_area = [got for got in leftovers if _share_area(want, got)]
        if len(same_area) == 1 and (
            sum(_share_area(other, same_area[0]) for other in unpaired) == 1
        ):
            pairs.append((want, same_area[0]))
            leftovers.remove(same_area[0])
        else:
            missing.append(want.name)
    return pairs, missing, [unit.name for unit in leftovers]


def _share_area(want: ExpectedUnitType, got: ExtractedUnitType) -> bool:
    """True if any area of want (total or private) is within tolerance of any area of got."""
    wanted = [a for a in (want.total_area_m2, want.private_area_m2) if a is not None]
    gotten = [a for a in (got.total_area_m2, got.private_area_m2) if a is not None]
    return any(abs(Decimal(str(w)) - g) <= AREA_TOLERANCE for w in wanted for g in gotten)


def score_page(
    label: ExtractionLabel, extracted: ExtractedProject | None, error: str | None = None
) -> PageScore:
    """Compare one extraction with its label; a failed extraction found nothing."""
    found = list(extracted.unit_types) if extracted is not None else []
    pairs, missing, extra = pair_unit_types(label.unit_types, found)
    problems = [f"missing unit type {name!r}" for name in missing]
    problems += [f"extra unit type {name!r}" for name in extra]
    prices_ok = fields_ok = names_exact = 0
    for want, got in pairs:
        names_exact += normalize_unit_type_name(want.name) == normalize_unit_type_name(got.name)
        if want.price_cop == got.price_cop:
            prices_ok += 1
        else:
            problems.append(f"{want.name}: price {got.price_cop} != {want.price_cop}")
        for field, ok in _fields(want, got):
            if ok:
                fields_ok += 1
            else:
                problems.append(
                    f"{want.name}: {field} {getattr(got, field)} != {getattr(want, field)}"
                )
    project_ok = (
        extracted is not None
        and _same(label.name, extracted.name)
        and _same(label.neighborhood, extracted.neighborhood)
    )
    if extracted is not None and not project_ok:
        problems.append(
            f"project {extracted.name!r} / {extracted.neighborhood!r} != "
            f"{label.name!r} / {label.neighborhood!r}"
        )
    return PageScore(
        case_id=label.case_id,
        expected=len(label.unit_types),
        found=len(found),
        matched=len(pairs),
        names_exact=names_exact,
        prices_ok=prices_ok,
        fields_ok=fields_ok,
        project_ok=project_ok,
        problems=problems,
        pairing={want.name: got.name for want, got in pairs},
        error=error,
    )


def total(scores: Sequence[PageScore]) -> Metrics:
    """Sum page scores into the run's metrics."""
    return Metrics(
        pages=len(scores),
        expected=sum(s.expected for s in scores),
        found=sum(s.found for s in scores),
        matched=sum(s.matched for s in scores),
        names_exact=sum(s.names_exact for s in scores),
        prices_ok=sum(s.prices_ok for s in scores),
        fields_ok=sum(s.fields_ok for s in scores),
        projects_ok=sum(s.project_ok for s in scores),
        perfect_pages=sum(s.perfect for s in scores),
        errors=sum(s.error is not None for s in scores),
    )


def _fields(want: ExpectedUnitType, got: ExtractedUnitType) -> list[tuple[str, bool]]:
    return [
        ("total_area_m2", _area_ok(want.total_area_m2, got.total_area_m2)),
        ("private_area_m2", _area_ok(want.private_area_m2, got.private_area_m2)),
        ("bedrooms", want.bedrooms == got.bedrooms),
        ("bathrooms", want.bathrooms == got.bathrooms),
    ]


def _area_ok(want: float | None, got: Decimal | None) -> bool:
    if want is None or got is None:
        return want is None and got is None
    return abs(Decimal(str(want)) - got) <= AREA_TOLERANCE


def _same(want: str | None, got: str | None) -> bool:
    return normalize((want or "").strip()) == normalize((got or "").strip())
