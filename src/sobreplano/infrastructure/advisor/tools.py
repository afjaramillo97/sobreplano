"""The advisor's seven tools: project search and comparison, and the financial simulations."""

from collections.abc import Callable
from decimal import Decimal

from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt.tool_node import ToolInvocationError
from pydantic import BaseModel

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.finance import (
    down_payment_plan,
    max_affordable_price,
    simulate_mortgage,
)
from sobreplano.domain.listings import ProjectFilters, ProjectSort
from sobreplano.domain.ports import ProjectListingQuery
from sobreplano.infrastructure.advisor.tool_schemas import (
    DEFAULT_SEARCH_LIMIT,
    AffordabilityOut,
    BestPricePerM2Out,
    CompareProjectsArgs,
    CompareProjectsOut,
    ComparisonRowOut,
    DeveloperOut,
    DownPaymentPlanArgs,
    DownPaymentPlanOut,
    GetProjectArgs,
    GetProjectOut,
    ListDevelopersArgs,
    ListDevelopersOut,
    MaxAffordablePriceArgs,
    MortgageSimulationOut,
    ProjectDetailOut,
    ProjectOut,
    SearchProjectsArgs,
    SearchProjectsOut,
    SimulateMortgageArgs,
    UnitTypeOut,
)

SEARCH_DESCRIPTION = (
    "Search new off-plan housing projects in the Aburrá Valley. Every filter is optional. "
    "Prices are in COP and are published 'from' prices. Returns the total number of matches "
    "and, per project, the unit types that meet the filters with their latest price and "
    "its observation date, price per m² and the change since the first observed price."
)
GET_PROJECT_DESCRIPTION = (
    "Get one project by slug with, per unit type, the first, minimum and maximum observed "
    "price, the number of observations and the days on which the price changed (last 20). "
    "Use it to explain how much a project has risen. Returns found=false if the slug is unknown."
)
COMPARE_DESCRIPTION = (
    "Compare two or three projects by slug: one row per unit type with price, area, price per "
    "m² and change since the first price, plus the unit type with the lowest price per m². "
    "Unknown slugs are listed in not_found."
)
DEVELOPERS_DESCRIPTION = "List the developers (constructoras) with their slug and project count."
MORTGAGE_DESCRIPTION = (
    "Simulate a fixed-payment home loan: monthly payment, total paid, total interest and the "
    "minimum monthly income needed (payment is at most 40 % of income). Approximate: no "
    "insurance or closing costs. Never guess the rate; ask the user for it."
)
AFFORDABILITY_DESCRIPTION = (
    "Compute the highest home price a household can buy from its monthly income and savings, "
    "and whether income or savings is the limit. Never guess the rate; ask the user for it."
)
DOWN_PAYMENT_DESCRIPTION = (
    "Plan the down payment of an off-plan home: the monthly installment to pay until delivery "
    "and the amount left for the loan. The default down payment is 30 % of the price."
)


def handle_tool_error(error: DomainValidationError | ToolInvocationError) -> str:
    """Turn a bad argument into a message the model can read and correct.

    The annotation is what ToolNode uses to decide which exceptions reach this handler; any
    other exception propagates and the route answers 503.
    """
    if isinstance(error, ToolInvocationError):
        return error.message
    return f"Invalid arguments: {error}"


def _json(result: BaseModel) -> str:
    return result.model_dump_json(exclude_none=True)


def _decimal(value: float) -> Decimal:
    # Through str so 12.5 becomes Decimal("12.5"), not its binary expansion.
    return Decimal(str(value))


def _tool(
    func: Callable[..., str], name: str, description: str, schema: type[BaseModel]
) -> BaseTool:
    return StructuredTool.from_function(
        func=func, name=name, description=description, args_schema=schema
    )


def build_tools(query: ProjectListingQuery) -> list[BaseTool]:
    """Build the seven tools over a ProjectListingQuery (the request's session).

    Each tool's arguments are validated by its Pydantic schema before the function runs.
    """

    def search_projects(
        municipality: Municipality | None = None,
        developer: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_bedrooms: int | None = None,
        min_area: float | None = None,
        max_area: float | None = None,
        sort: str = "name",
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> str:
        filters = ProjectFilters(
            municipality=municipality,
            developer=developer,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            min_area=_decimal(min_area) if min_area is not None else None,
            max_area=_decimal(max_area) if max_area is not None else None,
        )
        page = query.list_projects(filters=filters, sort=ProjectSort(sort), limit=limit, offset=0)
        return _json(
            SearchProjectsOut(
                total=page.total, projects=[ProjectOut.from_domain(p) for p in page.items]
            )
        )

    def get_project(slug: str) -> str:
        detail = query.get_project(slug)
        if detail is None:
            return _json(GetProjectOut(found=False))
        return _json(GetProjectOut(found=True, project=ProjectDetailOut.from_detail(detail)))

    def compare_projects(slugs: list[str]) -> str:
        rows: list[ComparisonRowOut] = []
        not_found: list[str] = []
        best: BestPricePerM2Out | None = None
        for slug in dict.fromkeys(slugs):  # drops repeated slugs, keeps the order
            detail = query.get_project(slug)
            if detail is None:
                not_found.append(slug)
                continue
            project = detail.project
            for unit in project.unit_types:
                rows.append(
                    ComparisonRowOut(
                        **UnitTypeOut.from_domain(unit).model_dump(),
                        project_slug=project.slug,
                        project_name=project.name,
                        municipality=project.municipality.value,
                        source_url=project.source_url,
                    )
                )
                per_m2 = unit.price_per_m2_cop
                if per_m2 is not None and (best is None or per_m2 < best.price_per_m2_cop):
                    best = BestPricePerM2Out(
                        project_slug=project.slug, unit_type=unit.name, price_per_m2_cop=per_m2
                    )
        return _json(CompareProjectsOut(rows=rows, lowest_price_per_m2=best, not_found=not_found))

    def list_developers() -> str:
        return _json(
            ListDevelopersOut(
                developers=[DeveloperOut.from_domain(d) for d in query.list_developers()]
            )
        )

    def simulate_mortgage_tool(
        price_cop: int, annual_rate_ea_pct: float, years: int, down_payment_pct: float
    ) -> str:
        return _json(
            MortgageSimulationOut.from_domain(
                simulate_mortgage(
                    price_cop,
                    annual_rate_ea_pct=_decimal(annual_rate_ea_pct),
                    years=years,
                    down_payment_pct=_decimal(down_payment_pct),
                )
            )
        )

    def max_affordable_price_tool(
        monthly_income_cop: int,
        savings_cop: int,
        annual_rate_ea_pct: float,
        years: int,
        down_payment_pct: float,
    ) -> str:
        return _json(
            AffordabilityOut.from_domain(
                max_affordable_price(
                    monthly_income_cop,
                    savings_cop,
                    annual_rate_ea_pct=_decimal(annual_rate_ea_pct),
                    years=years,
                    down_payment_pct=_decimal(down_payment_pct),
                )
            )
        )

    def down_payment_plan_tool(
        price_cop: int, months_until_delivery: int, down_payment_pct: float, upfront_cop: int
    ) -> str:
        return _json(
            DownPaymentPlanOut.from_domain(
                down_payment_plan(
                    price_cop,
                    down_payment_pct=_decimal(down_payment_pct),
                    months=months_until_delivery,
                    upfront_cop=upfront_cop,
                )
            )
        )

    return [
        _tool(search_projects, "search_projects", SEARCH_DESCRIPTION, SearchProjectsArgs),
        _tool(get_project, "get_project", GET_PROJECT_DESCRIPTION, GetProjectArgs),
        _tool(compare_projects, "compare_projects", COMPARE_DESCRIPTION, CompareProjectsArgs),
        _tool(list_developers, "list_developers", DEVELOPERS_DESCRIPTION, ListDevelopersArgs),
        _tool(
            simulate_mortgage_tool, "simulate_mortgage", MORTGAGE_DESCRIPTION, SimulateMortgageArgs
        ),
        _tool(
            max_affordable_price_tool,
            "max_affordable_price",
            AFFORDABILITY_DESCRIPTION,
            MaxAffordablePriceArgs,
        ),
        _tool(
            down_payment_plan_tool,
            "down_payment_plan",
            DOWN_PAYMENT_DESCRIPTION,
            DownPaymentPlanArgs,
        ),
    ]
