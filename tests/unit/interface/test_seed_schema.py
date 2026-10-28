"""Unit tests for the seed file schema; the data below is fictitious test data."""

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from sobreplano.interface.cli.seed_schema import SeedFile

VALID: dict[str, Any] = {
    "projects": [
        {
            "developer": {
                "name": "Constructora Ficticia",
                "slug": "ficticia",
                "website_url": "https://example.com",
            },
            "name": "Proyecto Ficticio",
            "slug": "proyecto-ficticio",
            "municipality": "sabaneta",
            "neighborhood": "Centro",
            "lat": 6.15,
            "lon": -75.61,
            "source_url": "https://example.com/proyecto",
            "unit_types": [
                {
                    "name": "Tipo A",
                    "private_area_m2": 55.5,
                    "bedrooms": 2,
                    "bathrooms": 2,
                    "observation": {
                        "price_cop": 320000000,
                        "observed_at": "2026-10-28T10:00:00-05:00",
                        "source_url": "https://example.com/proyecto",
                    },
                }
            ],
        }
    ]
}


def parse(data: dict[str, Any]) -> SeedFile:
    return SeedFile.model_validate(data)


_DELETE = object()


def with_change(path: list[str | int], value: object) -> dict[str, Any]:
    """A copy of VALID with the value at path (relative to the first project) replaced."""
    data = copy.deepcopy(VALID)
    target: Any = data["projects"][0]
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return data


def test_valid_file_parses() -> None:
    assert parse(VALID).projects[0].slug == "proyecto-ficticio"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param(["unit_types"], [], id="no-unit-types"),
        pytest.param(["lat"], -75.61, id="swapped-coordinates"),
        pytest.param(["municipality"], "bogota", id="unknown-municipality"),
        pytest.param(["slug"], "Con Espacios", id="bad-slug"),
        pytest.param(["source_url"], "no-es-url", id="bad-url"),
        pytest.param(["extra_field"], 1, id="unknown-field"),
        pytest.param(["unit_types", 0, "observation", "price_cop"], 0, id="zero-price"),
        pytest.param(
            ["unit_types", 0, "observation", "observed_at"],
            "2026-10-28T10:00:00",
            id="naive-datetime",
        ),
        pytest.param(["unit_types", 0, "private_area_m2"], _DELETE, id="no-areas"),
        pytest.param(["unit_types", 0, "private_area_m2"], 0, id="zero-area"),
    ],
)
def test_invalid_files_are_rejected(path: list[str | int], value: object) -> None:
    with pytest.raises(ValidationError):
        parse(with_change(path, value))


def test_duplicate_unit_type_names_are_rejected() -> None:
    data = copy.deepcopy(VALID)
    unit_types: list[Any] = data["projects"][0]["unit_types"]
    unit_types.append(copy.deepcopy(unit_types[0]))
    with pytest.raises(ValidationError):
        parse(data)


def test_duplicate_project_slugs_are_rejected() -> None:
    data = copy.deepcopy(VALID)
    data["projects"].append(copy.deepcopy(data["projects"][0]))
    with pytest.raises(ValidationError):
        parse(data)


def test_same_developer_in_two_projects_must_match() -> None:
    data = copy.deepcopy(VALID)
    second = copy.deepcopy(data["projects"][0])
    second["slug"] = "otro-proyecto"
    second["developer"]["name"] = "Otro nombre"
    data["projects"].append(second)
    with pytest.raises(ValidationError):
        parse(data)
