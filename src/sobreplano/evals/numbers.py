"""Amounts in COP and percentages written in an answer, in Spanish or English number formats."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

MIN_AMOUNT_COP = Decimal(1_000_000)

# A number with optional thousands separators and decimals, then an optional unit. The unit
# "M" is case-sensitive so "58 m²" is never read as millions.
_FIGURE = re.compile(
    r"(?<![\w.,])(?P<number>\d+(?:[.,]\d+)*)"
    r"(?P<unit>\s*%"
    r"|\s*mil\s+millones\b"
    r"|\s*(?:millones|millón|millon|millions?)\b"
    r"|\s*(?:MM|M)(?![\w²])"
    r")?",
    re.IGNORECASE,
)
_CASE_SENSITIVE_UNITS = frozenset({"M", "MM"})
_MULTIPLIERS = {
    "mil millones": Decimal(1_000_000_000),
    "millones": Decimal(1_000_000),
    "millón": Decimal(1_000_000),
    "millon": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "millions": Decimal(1_000_000),
    "mm": Decimal(1_000_000),
    "m": Decimal(1_000_000),
}

Kind = Literal["amount", "percent"]


@dataclass(frozen=True)
class Figure:
    """A figure found in a text: its value and the text it was read from."""

    kind: Kind
    value: Decimal  # pesos for an amount, percentage points for a percent
    raw: str


def parse_number(token: str) -> Decimal:
    """Read a number written as 445.000.000, 445,000,000, 8,54, 8.54 or 1.234,5.

    Groups of exactly three digits after every separator are thousands; otherwise the last
    separator is the decimal point. "8.540" therefore reads as 8540, as in Spanish.
    """
    separators = [c for c in token if c in ".,"]
    if not separators:
        return Decimal(token)
    groups = re.split(r"[.,]", token)
    if len(set(separators)) == 1 and all(len(group) == 3 for group in groups[1:]):
        return Decimal("".join(groups))
    decimal_mark = separators[-1]
    whole, _, fraction = token.rpartition(decimal_mark)
    return Decimal(re.sub(r"[.,]", "", whole) + "." + fraction)


def find_figures(text: str) -> list[Figure]:
    """Every amount of at least 1.000.000 COP and every percentage in text, in order.

    Numbers below 1.000.000 without "%" are ignored: years, bedrooms, areas, months.
    """
    figures: list[Figure] = []
    for match in _FIGURE.finditer(text):
        value, unit = _read(match)
        if unit == "%":
            figures.append(Figure("percent", value, match.group(0).strip()))
        elif value >= MIN_AMOUNT_COP:
            figures.append(Figure("amount", value, match.group(0).strip()))
    return figures


def all_numbers(text: str) -> list[Decimal]:
    """Every number in text with its unit applied, whatever its size.

    Used on tool results and user messages, the sources an answer's figures must come from.
    """
    return [_read(match)[0] for match in _FIGURE.finditer(text)]


def _read(match: re.Match[str]) -> tuple[Decimal, str]:
    value = parse_number(match.group("number"))
    unit = re.sub(r"\s+", " ", (match.group("unit") or "").strip())
    if unit.upper() in _CASE_SENSITIVE_UNITS and unit != unit.upper():
        # "m" or "mm" in lowercase is a unit of length, not millions.
        return value, ""
    if unit == "%":
        return value, "%"
    multiplier = _MULTIPLIERS.get(unit.lower())
    return (value * multiplier, unit) if multiplier is not None else (value, "")
