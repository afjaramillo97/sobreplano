"""Unit tests for the advisor's tools over an in-memory ProjectListingQuery."""

import json
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

# langgraph.graph ships without stubs and its builder generics are partly unknown to pyright.
from langgraph.graph import START, MessagesState, StateGraph  # pyright: ignore[reportMissingTypeStubs]
from langgraph.prebuilt import ToolNode

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.listings import (
    DeveloperSummary,
    LatestPrice,
    PricePoint,
    ProjectDetail,
    ProjectFilters,
    ProjectListing,
    ProjectPage,
    ProjectSort,
    UnitTypeDetail,
    UnitTypeListing,
)
from sobreplano.domain.pricing import ObservationSource
from sobreplano.infrastructure.advisor.tool_schemas import MAX_PRICE_CHANGES
from sobreplano.infrastructure.advisor.tools import build_tools, handle_tool_error

SRC = ObservationSource.SCRAPER


def point(day: int, price: int) -> PricePoint:
    return PricePoint(observed_on=date(2026, 11, day), price_cop=price, source=SRC)


def make_unit(
    name: str, history: list[PricePoint], area: str | None = "50.00", bedrooms: int | None = 2
) -> UnitTypeDetail:
    latest = history[-1] if history else None
    listing = UnitTypeListing(
        id=uuid4(),
        name=name,
        private_area_m2=Decimal(area) if area else None,
        built_area_m2=None if area else Decimal("60.00"),
        bedrooms=bedrooms,
        bathrooms=2,
        latest_price=LatestPrice(latest.price_cop, latest.observed_on, SRC) if latest else None,
        first_price=history[0] if history else None,
    )
    return UnitTypeDetail(listing=listing, history=history)


def make_detail(slug: str, name: str, units: list[UnitTypeDetail]) -> ProjectDetail:
    listing = ProjectListing(
        id=uuid4(),
        slug=slug,
        name=name,
        developer_name="Constructora X",
        developer_slug="constructora-x",
        municipality=Municipality.SABANETA,
        neighborhood="Aves María",
        location=None,
        source_url=f"https://example.com/{slug}",
        unit_types=[unit.listing for unit in units],
    )
    return ProjectDetail(project=listing, unit_types=units)


class FakeQuery:
    """Serves canned projects and records how list_projects was called."""

    def __init__(self, details: list[ProjectDetail]) -> None:
        self.details = {detail.project.slug: detail for detail in details}
        self.calls: list[dict[str, Any]] = []

    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        self.calls.append({"filters": filters, "sort": sort, "limit": limit, "offset": offset})
        items = [detail.project for detail in self.details.values()]
        return ProjectPage(items=items[:limit], total=len(items))

    def get_project(self, slug: str) -> ProjectDetail | None:
        return self.details.get(slug)

    def list_developers(self) -> list[DeveloperSummary]:
        return [
            DeveloperSummary(
                slug="constructora-x",
                name="Constructora X",
                website_url="https://example.com",
                projects=3,
            )
        ]


ALPHA = make_detail(
    "alpha",
    "Alpha",
    [
        make_unit("Tipo 1", [point(1, 400_000_000), point(2, 400_000_000), point(3, 420_000_000)]),
        make_unit("Tipo 2", [point(1, 500_000_000)], area="80.00"),
    ],
)
BETA = make_detail(
    "beta", "Beta", [make_unit("Tipo A", [point(1, 300_000_000), point(3, 330_000_000)])]
)


@pytest.fixture
def query() -> FakeQuery:
    return FakeQuery([ALPHA, BETA])


@pytest.fixture
def tools(query: FakeQuery) -> dict[str, BaseTool]:
    return {tool.name: tool for tool in build_tools(query)}


def call(tools: dict[str, BaseTool], tool_name: str, **args: Any) -> dict[str, Any]:
    return json.loads(tools[tool_name].invoke(args))


def test_there_are_seven_tools_with_descriptions(tools: dict[str, BaseTool]) -> None:
    assert set(tools) == {
        "search_projects",
        "get_project",
        "compare_projects",
        "list_developers",
        "simulate_mortgage",
        "max_affordable_price",
        "down_payment_plan",
    }
    assert all(len(tool.description) > 40 for tool in tools.values())


def test_search_passes_filters_sort_and_default_limit(
    tools: dict[str, BaseTool], query: FakeQuery
) -> None:
    call(
        tools,
        "search_projects",
        name="Réflex",
        municipality="sabaneta",
        max_price=450_000_000,
        min_bedrooms=3,
        min_area=45.5,
        sort="price",
    )
    [seen] = query.calls
    assert seen["filters"] == ProjectFilters(
        name="Réflex",
        municipality=Municipality.SABANETA,
        max_price=450_000_000,
        min_bedrooms=3,
        min_area=Decimal("45.5"),
    )
    assert seen["sort"] is ProjectSort.PRICE
    assert (seen["limit"], seen["offset"]) == (5, 0)


def test_search_output_has_price_date_link_and_no_nulls(tools: dict[str, BaseTool]) -> None:
    result = call(tools, "search_projects", limit=1)
    assert result["total"] == 2
    [project] = result["projects"]
    assert project["source_url"] == "https://example.com/alpha"
    first = project["unit_types"][0]
    assert first["latest_price_cop"] == 420_000_000
    assert first["price_observed_on"] == "2026-11-03"
    assert first["price_per_m2_cop"] == 8_400_000
    assert first["change_since_first_pct"] == 5.0
    assert "location" not in project and "neighborhood" in project
    # A single observation has no change: the field is left out, not sent as null.
    assert "change_since_first_pct" not in project["unit_types"][1]


def test_search_limit_above_ten_is_rejected(tools: dict[str, BaseTool]) -> None:
    with pytest.raises(ValueError, match="limit"):
        tools["search_projects"].invoke({"limit": 11})


def test_get_project_compacts_history_to_the_days_the_price_changed(
    tools: dict[str, BaseTool],
) -> None:
    result = call(tools, "get_project", slug="alpha")
    unit = result["project"]["unit_types"][0]
    assert result["found"] is True
    assert (unit["first_price_cop"], unit["first_observed_on"]) == (400_000_000, "2026-11-01")
    assert (unit["min_price_cop"], unit["max_price_cop"]) == (400_000_000, 420_000_000)
    assert unit["observations"] == 3
    assert unit["price_changes"] == [{"observed_on": "2026-11-03", "price_cop": 420_000_000}]


def test_get_project_keeps_only_the_last_twenty_changes(query: FakeQuery) -> None:
    history = [point(1 + i % 28, 400_000_000 + i * 1_000_000) for i in range(30)]
    query.details["long"] = make_detail("long", "Long", [make_unit("T", history)])
    tools = {tool.name: tool for tool in build_tools(query)}
    unit = call(tools, "get_project", slug="long")["project"]["unit_types"][0]
    assert len(unit["price_changes"]) == MAX_PRICE_CHANGES
    assert unit["price_changes"][-1]["price_cop"] == history[-1].price_cop
    assert unit["observations"] == 30


def test_get_project_unknown_slug(tools: dict[str, BaseTool]) -> None:
    assert call(tools, "get_project", slug="nope") == {"found": False}


def test_compare_lists_rows_and_the_lowest_price_per_m2(tools: dict[str, BaseTool]) -> None:
    result = call(tools, "compare_projects", slugs=["alpha", "beta"])
    assert [(row["project_slug"], row["name"]) for row in result["rows"]] == [
        ("alpha", "Tipo 1"),
        ("alpha", "Tipo 2"),
        ("beta", "Tipo A"),
    ]
    # Alpha Tipo 2: 500M / 80 m² = 6.25M, below Beta Tipo A (6.6M) and Alpha Tipo 1 (8.4M).
    assert result["lowest_price_per_m2"] == {
        "project_slug": "alpha",
        "unit_type": "Tipo 2",
        "price_per_m2_cop": 6_250_000,
    }
    assert "not_found" not in result or result["not_found"] == []


def test_compare_reports_unknown_slugs(tools: dict[str, BaseTool]) -> None:
    result = call(tools, "compare_projects", slugs=["alpha", "nope"])
    assert result["not_found"] == ["nope"]
    assert {row["project_slug"] for row in result["rows"]} == {"alpha"}


@pytest.mark.parametrize("slugs", [["alpha"], ["a", "b", "c", "d"]])
def test_compare_needs_two_or_three_slugs(tools: dict[str, BaseTool], slugs: list[str]) -> None:
    with pytest.raises(ValueError, match="slugs"):
        tools["compare_projects"].invoke({"slugs": slugs})


def test_list_developers(tools: dict[str, BaseTool]) -> None:
    assert call(tools, "list_developers") == {
        "developers": [{"slug": "constructora-x", "name": "Constructora X", "projects": 3}]
    }


def test_simulate_mortgage_matches_the_domain_example(tools: dict[str, BaseTool]) -> None:
    result = call(
        tools, "simulate_mortgage", price_cop=400_000_000, annual_rate_ea_pct=12, years=20
    )
    assert result["monthly_payment_cop"] == 2_964_145
    assert result["down_payment_cop"] == 120_000_000  # 30 % by default


def test_max_affordable_price_matches_the_domain_example(tools: dict[str, BaseTool]) -> None:
    result = call(
        tools,
        "max_affordable_price",
        monthly_income_cop=12_000_000,
        savings_cop=150_000_000,
        annual_rate_ea_pct=12,
        years=20,
    )
    assert (result["max_price_cop"], result["limited_by"]) == (500_000_000, "savings")


def test_down_payment_plan_matches_the_domain_example(tools: dict[str, BaseTool]) -> None:
    result = call(
        tools,
        "down_payment_plan",
        price_cop=400_000_000,
        months_until_delivery=24,
        upfront_cop=10_000_000,
    )
    assert result["monthly_installment_cop"] == 4_583_333
    assert result["loan_at_delivery_cop"] == 280_000_000


def test_the_rate_has_no_default(tools: dict[str, BaseTool]) -> None:
    with pytest.raises(ValueError, match="annual_rate_ea_pct"):
        tools["simulate_mortgage"].invoke({"price_cop": 400_000_000, "years": 20})


def run_in_tool_node(tools: dict[str, BaseTool], name: str, args: dict[str, Any]) -> ToolMessage:
    """Run one tool call through a ToolNode inside a minimal graph, as the advisor does."""
    node = ToolNode(list(tools.values()), handle_tool_errors=handle_tool_error)
    builder = StateGraph(MessagesState)
    builder.add_node("tools", node)  # pyright: ignore[reportUnknownMemberType]
    builder.add_edge(START, "tools")
    graph = builder.compile()  # pyright: ignore[reportUnknownMemberType]
    message = AIMessage(content="", tool_calls=[{"id": "1", "name": name, "args": args}])
    result = graph.invoke({"messages": [message]})  # pyright: ignore[reportUnknownMemberType]
    reply = result["messages"][-1]
    assert isinstance(reply, ToolMessage)
    return reply


def test_domain_validation_error_goes_back_to_the_model(tools: dict[str, BaseTool]) -> None:
    reply = run_in_tool_node(
        tools,
        "simulate_mortgage",
        {"price_cop": 400_000_000, "annual_rate_ea_pct": 12, "years": 50},
    )
    assert reply.status == "error"
    assert "years must be between 5 and 30" in str(reply.content)


def test_inverted_price_range_goes_back_to_the_model(tools: dict[str, BaseTool]) -> None:
    reply = run_in_tool_node(tools, "search_projects", {"min_price": 5, "max_price": 1})
    assert reply.status == "error"
    assert "min_price must be <= max_price" in str(reply.content)


def test_invalid_argument_type_goes_back_to_the_model(tools: dict[str, BaseTool]) -> None:
    reply = run_in_tool_node(tools, "get_project", {})
    assert reply.status == "error"
    assert "slug" in str(reply.content)


def test_other_errors_are_not_swallowed(query: FakeQuery) -> None:
    def broken(slug: str) -> None:
        raise RuntimeError("database down")

    query.get_project = broken  # type: ignore[method-assign]
    tools = {tool.name: tool for tool in build_tools(query)}
    with pytest.raises(RuntimeError, match="database down"):
        run_in_tool_node(tools, "get_project", {"slug": "alpha"})
