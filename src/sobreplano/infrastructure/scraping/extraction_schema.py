"""Pydantic schema of the LLM extraction (strict structured output) and its domain mapping."""

from decimal import Decimal

from pydantic import BaseModel

from sobreplano.domain import scraping


class ExtractedUnitType(BaseModel):
    """One unit type block of the page. Every field is required and nullable (strict mode)."""

    name: str
    price_cop: int | None  # "Desde $506.100.000" -> 506100000; None without a peso price
    total_area_m2: float | None  # float, not Decimal: portable across strict modes
    private_area_m2: float | None
    bedrooms: int | None  # the minimum when the page gives a range
    bathrooms: int | None


class ExtractedProject(BaseModel):
    """The project as the model reads it; municipality, slug and location are not asked for."""

    name: str
    neighborhood: str | None  # sector or neighborhood, e.g. "Pan de Azúcar"
    unit_types: list[ExtractedUnitType]

    def to_domain(self) -> scraping.ExtractedProject:
        """The same data as domain dataclasses, with areas as Decimal."""
        return scraping.ExtractedProject(
            name=self.name,
            neighborhood=self.neighborhood,
            unit_types=tuple(
                scraping.ExtractedUnitType(
                    name=unit.name,
                    price_cop=unit.price_cop,
                    total_area_m2=_to_decimal(unit.total_area_m2),
                    private_area_m2=_to_decimal(unit.private_area_m2),
                    bedrooms=unit.bedrooms,
                    bathrooms=unit.bathrooms,
                )
                for unit in self.unit_types
            ),
        )

    @classmethod
    def from_domain(cls, project: scraping.ExtractedProject) -> "ExtractedProject":
        """Back from domain dataclasses, to store the payload as JSON."""
        return cls(
            name=project.name,
            neighborhood=project.neighborhood,
            unit_types=[
                ExtractedUnitType(
                    name=unit.name,
                    price_cop=unit.price_cop,
                    total_area_m2=_to_float(unit.total_area_m2),
                    private_area_m2=_to_float(unit.private_area_m2),
                    bedrooms=unit.bedrooms,
                    bathrooms=unit.bathrooms,
                )
                for unit in project.unit_types
            ],
        )


def _to_decimal(value: float | None) -> Decimal | None:
    # Through str, so 55.58 becomes Decimal("55.58") and not its binary approximation.
    return None if value is None else Decimal(str(value))


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)
