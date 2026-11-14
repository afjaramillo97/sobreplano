"""Unit tests for reading COP amounts and percentages out of an answer."""

from decimal import Decimal

import pytest

from sobreplano.evals.numbers import Figure, all_numbers, find_figures, parse_number


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Desde $445.000.000", 445_000_000),
        ("cuesta 445.000.000 COP", 445_000_000),
        ("unos 445 millones", 445_000_000),
        ("445M", 445_000_000),
        ("cuota de 5.562.500 al mes", 5_562_500),
        ("from $445,000,000", 445_000_000),
        ("about 1.5 million pesos", 1_500_000),
        ("5,56 millones", 5_560_000),
        ("1 millón", 1_000_000),
        ("1,2 mil millones", 1_200_000_000),
        ("cuota de $2.964.145", 2_964_145),
    ],
)
def test_amounts(text: str, value: int) -> None:
    assert find_figures(text) == [Figure("amount", Decimal(value), find_figures(text)[0].raw)]


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("una tasa del 8,54 %", "8.54"),
        ("rate of 8.54%", "8.54"),
        ("12 % EA", "12"),
        ("subió 8,6%", "8.6"),
    ],
)
def test_percents(text: str, value: str) -> None:
    [figure] = find_figures(text)
    assert (figure.kind, figure.value) == ("percent", Decimal(value))


@pytest.mark.parametrize(
    "text",
    [
        "a 20 años",
        "entrega en 2026",
        "3 alcobas y 2 baños",
        "58 m² de área privada",
        "58 m2",
        "24 meses",
        "999.999 pesos",
        "5 mm de espesor",
    ],
)
def test_small_numbers_years_and_areas_are_ignored(text: str) -> None:
    assert find_figures(text) == []


def test_several_figures_keep_their_order_and_raw_text() -> None:
    figures = find_figures("Tipo A: $380.000.000 (subió 8,57 %); Tipo B: 445 millones.")
    assert [(f.kind, f.value, f.raw) for f in figures] == [
        ("amount", Decimal(380_000_000), "380.000.000"),
        ("percent", Decimal("8.57"), "8,57 %"),
        ("amount", Decimal(445_000_000), "445 millones"),
    ]


@pytest.mark.parametrize(
    ("token", "value"),
    [
        ("445000000", "445000000"),
        ("445.000.000", "445000000"),
        ("445,000,000", "445000000"),
        ("8,54", "8.54"),
        ("8.54", "8.54"),
        ("1.234,5", "1234.5"),
        ("1,234.5", "1234.5"),
        ("8.540", "8540"),
    ],
)
def test_parse_number(token: str, value: str) -> None:
    assert parse_number(token) == Decimal(value)


def test_all_numbers_reads_json_tool_results_and_user_messages() -> None:
    tool_result = '{"price_cop":445000000,"years":20,"annual_rate_ea_pct":12.0}'
    assert all_numbers(tool_result) == [Decimal(445_000_000), Decimal(20), Decimal("12.0")]
    assert all_numbers("Gano 12 millones y tengo 150 ahorrados") == [
        Decimal(12_000_000),
        Decimal(150),
    ]
