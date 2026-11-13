"""Pydantic input and output models of the advisor's tools (constitution, principle 4)."""

from datetime import date
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.finance import (
    DEFAULT_DOWN_PAYMENT_PCT,
    Affordability,
    DownPaymentPlan,
    MortgageSimulation,
)
from sobreplano.domain.listings import (
    DeveloperSummary,
    PricePoint,
    ProjectDetail,
    ProjectListing,
    UnitTypeListing,
)

MAX_PRICE_CHANGES = 20  # most recent changes shown per unit type
DEFAULT_SEARCH_LIMIT = 5
MAX_SEARCH_LIMIT = 10
_DEFAULT_DOWN_PAYMENT = float(DEFAULT_DOWN_PAYMENT_PCT)


# --- Inputs: the field descriptions are what the model reads. ---


class SearchProjectsArgs(BaseModel):
    """Filters of search_projects; every filter is optional."""

    name: str | None = Field(
        None,
        description="Part of the project name, ignoring case and accents. Use it when the user "
        "names a project, to get its slug.",
    )
    municipality: Municipality | None = Field(None, description="Municipality of the valley.")
    developer: str | None = Field(None, description="Developer slug, from list_developers.")
    min_price: int | None = Field(None, gt=0, description="Minimum price in COP.")
    max_price: int | None = Field(None, gt=0, description="Maximum price in COP.")
    min_bedrooms: int | None = Field(None, gt=0, description="Minimum number of bedrooms.")
    min_area: float | None = Field(None, gt=0, description="Minimum area in m².")
    max_area: float | None = Field(None, gt=0, description="Maximum area in m².")
    sort: Literal["name", "price"] = Field(
        "name", description="'price' puts the lowest price first."
    )
    limit: int = Field(
        DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=MAX_SEARCH_LIMIT,
        description=f"Projects to return, 1 to {MAX_SEARCH_LIMIT}.",
    )


class GetProjectArgs(BaseModel):
    """Argument of get_project."""

    slug: str = Field(
        description="Project slug from search_projects; never guess it, search by name first."
    )


class CompareProjectsArgs(BaseModel):
    """Argument of compare_projects."""

    slugs: list[str] = Field(
        min_length=2,
        max_length=3,
        description="Two or three project slugs from search_projects; never guess them.",
    )


class ListDevelopersArgs(BaseModel):
    """list_developers takes no arguments."""


class SimulateMortgageArgs(BaseModel):
    """Arguments of simulate_mortgage."""

    price_cop: int = Field(description="Price of the home in COP.")
    annual_rate_ea_pct: float = Field(
        description="Annual effective rate (EA) in percent, e.g. 12 for 12 %. Ask the user."
    )
    years: int = Field(description="Loan term in years, 5 to 30.")
    down_payment_pct: float = Field(
        _DEFAULT_DOWN_PAYMENT, description="Down payment in percent of the price, 20 to 99."
    )


class MaxAffordablePriceArgs(BaseModel):
    """Arguments of max_affordable_price."""

    monthly_income_cop: int = Field(description="Household monthly income in COP.")
    savings_cop: int = Field(description="Savings available for the down payment, in COP.")
    annual_rate_ea_pct: float = Field(
        description="Annual effective rate (EA) in percent, e.g. 12 for 12 %. Ask the user."
    )
    years: int = Field(description="Loan term in years, 5 to 30.")
    down_payment_pct: float = Field(
        _DEFAULT_DOWN_PAYMENT, description="Down payment in percent of the price, 20 to 99."
    )


class DownPaymentPlanArgs(BaseModel):
    """Arguments of down_payment_plan."""

    price_cop: int = Field(description="Price of the home in COP.")
    months_until_delivery: int = Field(
        description="Months of construction left; the down payment is paid over them, 1 to 60."
    )
    down_payment_pct: float = Field(
        _DEFAULT_DOWN_PAYMENT, description="Down payment in percent of the price, 20 to 99."
    )
    upfront_cop: int = Field(
        0, description="Reservation or first payment, in COP, counted inside the down payment."
    )


# --- Outputs: serialized with exclude_none, so a missing value is not sent to the model. ---


class UnitTypeOut(BaseModel):
    """A unit type with its latest price."""

    name: str
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_m2: float | None = None  # private area if known, else built
    area_basis: str | None = None
    latest_price_cop: int | None = None
    price_observed_on: date | None = None
    price_per_m2_cop: int | None = None
    change_since_first_pct: float | None = None

    @classmethod
    def from_domain(cls, unit: UnitTypeListing) -> "UnitTypeOut":
        area = unit.private_area_m2 if unit.private_area_m2 is not None else unit.built_area_m2
        latest = unit.latest_price
        return cls(
            name=unit.name,
            bedrooms=unit.bedrooms,
            bathrooms=unit.bathrooms,
            area_m2=float(area) if area is not None else None,
            area_basis=unit.area_basis.value,
            latest_price_cop=latest.price_cop if latest else None,
            price_observed_on=latest.observed_on if latest else None,
            price_per_m2_cop=unit.price_per_m2_cop,
            change_since_first_pct=unit.change_since_first_pct,
        )


class ProjectOut(BaseModel):
    """A project with the unit types that matched."""

    slug: str
    name: str
    developer: str
    municipality: str
    neighborhood: str | None = None
    source_url: str
    unit_types: list[UnitTypeOut]

    @classmethod
    def from_domain(cls, project: ProjectListing) -> "ProjectOut":
        return cls(
            slug=project.slug,
            name=project.name,
            developer=project.developer_name,
            municipality=project.municipality.value,
            neighborhood=project.neighborhood,
            source_url=project.source_url,
            unit_types=[UnitTypeOut.from_domain(unit) for unit in project.unit_types],
        )


class SearchProjectsOut(BaseModel):
    """Result of search_projects; total counts every match, projects only the first `limit`."""

    total: int
    projects: list[ProjectOut]


class PriceChangeOut(BaseModel):
    """A day on which the price differs from the previous observation."""

    observed_on: date
    price_cop: int


class UnitTypeDetailOut(UnitTypeOut):
    """A unit type with a summary of its price history."""

    first_price_cop: int | None = None
    first_observed_on: date | None = None
    min_price_cop: int | None = None
    max_price_cop: int | None = None
    observations: int = 0
    price_changes: list[PriceChangeOut] = []  # last MAX_PRICE_CHANGES, oldest first


def price_changes(history: list[PricePoint]) -> list[PriceChangeOut]:
    """Days on which the price differs from the previous observation, last MAX_PRICE_CHANGES.

    Daily observations repeat the same price for weeks; keeping only the changes saves tokens.
    """
    changes = [
        PriceChangeOut(observed_on=current.observed_on, price_cop=current.price_cop)
        for previous, current in pairwise(history)
        if current.price_cop != previous.price_cop
    ]
    return changes[-MAX_PRICE_CHANGES:]


class ProjectDetailOut(ProjectOut):
    """A project whose unit types carry their price history summary."""

    unit_types: list[UnitTypeDetailOut]  # pyright: ignore[reportIncompatibleVariableOverride]

    @classmethod
    def from_detail(cls, detail: ProjectDetail) -> "ProjectDetailOut":
        project = detail.project
        units: list[UnitTypeDetailOut] = []
        for unit in detail.unit_types:
            prices = [point.price_cop for point in unit.history]
            first = unit.history[0] if unit.history else None
            units.append(
                UnitTypeDetailOut(
                    **UnitTypeOut.from_domain(unit.listing).model_dump(),
                    first_price_cop=first.price_cop if first else None,
                    first_observed_on=first.observed_on if first else None,
                    min_price_cop=min(prices) if prices else None,
                    max_price_cop=max(prices) if prices else None,
                    observations=len(prices),
                    price_changes=price_changes(unit.history),
                )
            )
        return cls(
            slug=project.slug,
            name=project.name,
            developer=project.developer_name,
            municipality=project.municipality.value,
            neighborhood=project.neighborhood,
            source_url=project.source_url,
            unit_types=units,
        )


class GetProjectOut(BaseModel):
    """Result of get_project; found is false when the slug does not exist."""

    found: bool
    project: ProjectDetailOut | None = None


class ComparisonRowOut(UnitTypeOut):
    """One unit type of one compared project."""

    project_slug: str
    project_name: str
    municipality: str
    source_url: str


class BestPricePerM2Out(BaseModel):
    """The unit type with the lowest price per m² among the compared ones."""

    project_slug: str
    unit_type: str
    price_per_m2_cop: int


class CompareProjectsOut(BaseModel):
    """Result of compare_projects."""

    rows: list[ComparisonRowOut]
    lowest_price_per_m2: BestPricePerM2Out | None = None
    not_found: list[str] = []


class DeveloperOut(BaseModel):
    """A developer and how many projects it has."""

    slug: str
    name: str
    projects: int

    @classmethod
    def from_domain(cls, developer: DeveloperSummary) -> "DeveloperOut":
        return cls(slug=developer.slug, name=developer.name, projects=developer.projects)


class ListDevelopersOut(BaseModel):
    """Result of list_developers."""

    developers: list[DeveloperOut]


class MortgageSimulationOut(BaseModel):
    """Result of simulate_mortgage; payments are fixed and exclude insurance."""

    model_config = ConfigDict(from_attributes=True)

    price_cop: int
    down_payment_cop: int
    loan_cop: int
    months: int
    monthly_payment_cop: int
    total_paid_cop: int
    total_interest_cop: int
    min_monthly_income_cop: int

    @classmethod
    def from_domain(cls, result: MortgageSimulation) -> "MortgageSimulationOut":
        return cls.model_validate(result)


class AffordabilityOut(BaseModel):
    """Result of max_affordable_price; limited_by says which limit binds."""

    model_config = ConfigDict(from_attributes=True)

    max_monthly_payment_cop: int
    max_loan_cop: int
    max_price_by_income_cop: int
    max_price_by_savings_cop: int
    max_price_cop: int
    limited_by: Literal["income", "savings"]

    @classmethod
    def from_domain(cls, result: Affordability) -> "AffordabilityOut":
        return cls.model_validate(result)


class DownPaymentPlanOut(BaseModel):
    """Result of down_payment_plan."""

    model_config = ConfigDict(from_attributes=True)

    down_payment_cop: int
    upfront_cop: int
    months: int
    monthly_installment_cop: int
    loan_at_delivery_cop: int

    @classmethod
    def from_domain(cls, result: DownPaymentPlan) -> "DownPaymentPlanOut":
        return cls.model_validate(result)
