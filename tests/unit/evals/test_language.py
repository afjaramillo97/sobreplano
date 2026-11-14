"""Unit tests for the Spanish-or-English guess."""

import pytest

from sobreplano.evals.language import detect_language


@pytest.mark.parametrize(
    "text",
    [
        "Encontré 2 proyectos en Sabaneta con 3 alcobas por menos de 450 millones.",
        "La cuota mensual sería de $2.964.145, sin seguros ni gastos.",
        "¿Qué tasa de interés te ofrece el banco?",
        "Solo puedo ayudarte con vivienda nueva en el Valle de Aburrá.",
    ],
)
def test_spanish(text: str) -> None:
    assert detect_language(text) == "es"


@pytest.mark.parametrize(
    "text",
    [
        "There are 2 projects in Envigado: Torres Demo and Parque Ficticio.",
        "With your income and savings, you could afford an apartment of about 400 million.",
        "What interest rate did the bank offer you?",
    ],
)
def test_english(text: str) -> None:
    assert detect_language(text) == "en"


def test_project_names_and_numbers_alone_default_to_spanish() -> None:
    assert detect_language("Torres Demo: $610.000.000") == "es"
