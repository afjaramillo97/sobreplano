"""Unit tests for redacting emails, phones and ID numbers, and for what is left untouched."""

import pytest

from sobreplano.domain.privacy import redact_personal_data


@pytest.mark.parametrize(
    ("text", "redacted", "kinds"),
    [
        ("Escríbeme a juan.perez+casa@example.com", "Escríbeme a [correo]", ["email"]),
        ("Mi celular 300 123 4567", "Mi celular [teléfono]", ["phone"]),
        ("Llámame al 3001234567.", "Llámame al [teléfono].", ["phone"]),
        ("Cel +57 300-123-4567", "Cel [teléfono]", ["phone"]),
        ("Cel 57 311.123.4567", "Cel [teléfono]", ["phone"]),
        ("Mi cédula es 43.123.456", "Mi cédula es [documento]", ["id_number"]),
        ("cedula: 43123456", "cedula: [documento]", ["id_number"]),
        ("CC 1234567890", "CC [documento]", ["id_number"]),
        ("C.C. 1.234.567.890", "C.C. [documento]", ["id_number"]),
        ("NIT 900123456", "NIT [documento]", ["id_number"]),
        (
            "mi pasaporte número AB es 12345678",
            "mi pasaporte número AB es [documento]",
            ["id_number"],
        ),
        ("ID 123456", "ID [documento]", ["id_number"]),
        (
            "juan@example.com, 300 123 4567 y cédula 43.123.456",
            "[correo], [teléfono] y cédula [documento]",
            ["email", "phone", "id_number"],
        ),
        ("documento 3001234567", "documento [teléfono]", ["phone"]),
    ],
)
def test_personal_data_is_redacted(text: str, redacted: str, kinds: list[str]) -> None:
    result = redact_personal_data(text)
    assert result.text == redacted
    assert result.kinds == kinds


@pytest.mark.parametrize(
    "text",
    [
        "Busco algo de $450.000.000",
        "Hasta 450 millones",
        "Gano 3.000.000 al mes",
        "El precio es 1.234.567.890",  # a 10-digit number with no keyword can be a price
        "Cuesta 380.000.000 y la cuota 3.050.000",
        "Apartamento de 58 m² en el piso 12, año 2028",
        "El documento 4 dice 45 millones",  # too short to be an ID
        "cédula, una dos tres cuatro 12345678",  # more than three words after the keyword
        "Mi tasa es 12,5 % a 20 años",
    ],
)
def test_prices_and_plain_numbers_are_not_redacted(text: str) -> None:
    result = redact_personal_data(text)
    assert result.text == text
    assert result.kinds == []
