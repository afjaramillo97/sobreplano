"""Unit tests for mentioned_projects: which projects of the turn's tools an answer names."""

from sobreplano.domain.advisor import ToolCallRecord
from sobreplano.infrastructure.advisor.mentions import MAX_MENTIONED, mentioned_projects
from sobreplano.infrastructure.advisor.tool_schemas import (
    CompareProjectsOut,
    ComparisonRowOut,
    GetProjectOut,
    ProjectDetailOut,
    ProjectOut,
    SearchProjectsOut,
)
from sobreplano.infrastructure.advisor.tools import DETAIL_LIMIT_RESULT


def project(slug: str, name: str) -> ProjectOut:
    return ProjectOut(
        slug=slug,
        name=name,
        developer="Constructora X",
        municipality="sabaneta",
        source_url=f"https://example.com/{slug}",
        unit_types=[],
    )


def search(*projects: tuple[str, str]) -> ToolCallRecord:
    out = SearchProjectsOut(total=len(projects), projects=[project(*p) for p in projects])
    return ToolCallRecord("search_projects", {}, out.model_dump_json(exclude_none=True))


def get(slug: str, name: str) -> ToolCallRecord:
    detail = ProjectDetailOut(
        slug=slug,
        name=name,
        developer="Constructora X",
        municipality="sabaneta",
        source_url=f"https://example.com/{slug}",
        unit_types=[],
    )
    out = GetProjectOut(found=True, project=detail)
    return ToolCallRecord("get_project", {"slug": slug}, out.model_dump_json(exclude_none=True))


def compare(*projects: tuple[str, str]) -> ToolCallRecord:
    rows = [
        ComparisonRowOut(
            name="Tipo A",
            project_slug=slug,
            project_name=name,
            municipality="envigado",
            source_url=f"https://example.com/{slug}",
        )
        for slug, name in projects
    ]
    out = CompareProjectsOut(rows=rows)
    return ToolCallRecord("compare_projects", {}, out.model_dump_json(exclude_none=True))


def test_names_with_accents_and_case_match_in_order_of_first_mention() -> None:
    calls = [search(("cipres", "Ciprés"), ("arrayanes", "Arrayanes del Sur"))]
    text = "ARRAYANES DEL SUR cuesta menos que cipres, y Ciprés está más cerca."
    assert mentioned_projects(text, calls) == ["arrayanes", "cipres"]


def test_accents_in_the_text_but_not_in_the_name_also_match() -> None:
    calls = [get("bosque-alto", "Bosque Alto")]
    assert mentioned_projects("Bósque Álto subió poco.", calls) == ["bosque-alto"]


def test_repeated_slugs_and_mentions_count_once() -> None:
    calls = [search(("vento", "Vento")), get("vento", "Vento"), compare(("vento", "Vento"))]
    assert mentioned_projects("Vento, Vento y otra vez Vento.", calls) == ["vento"]


def test_projects_the_text_does_not_name_are_left_out() -> None:
    calls = [search(("vento", "Vento"), ("cipres", "Ciprés"))]
    assert mentioned_projects("Solo te recomiendo Vento.", calls) == ["vento"]
    assert mentioned_projects("No encontré nada para ti.", calls) == []


def test_a_name_must_be_whole_words() -> None:
    calls = [search(("vento", "Vento"))]
    assert mentioned_projects("Hay un evento el sábado y Ventorrillo es otro.", calls) == []


def test_a_longer_name_does_not_also_count_as_the_shorter_one() -> None:
    calls = [search(("arrayanes", "Arrayanes"), ("arrayanes-del-sur", "Arrayanes del Sur"))]
    text = "Arrayanes del Sur es el más barato."
    assert mentioned_projects(text, calls) == ["arrayanes-del-sur"]


def test_error_outputs_and_other_tools_are_skipped() -> None:
    calls = [
        ToolCallRecord("search_projects", {}, "Error: invalid min_price"),
        ToolCallRecord("get_project", {}, DETAIL_LIMIT_RESULT),
        ToolCallRecord("get_project", {}, '{"found": false}'),
        ToolCallRecord("list_developers", {}, '{"developers": [{"slug": "x", "name": "Vento"}]}'),
        compare(("cipres", "Ciprés")),
    ]
    assert mentioned_projects("Vento y Ciprés.", calls) == ["cipres"]


def test_at_most_six_projects_in_order() -> None:
    names = [(f"p{i}", f"Torre {chr(ord('A') + i)}") for i in range(8)]
    text = ", ".join(name for _, name in reversed(names))
    result = mentioned_projects(text, [search(*names)])
    assert MAX_MENTIONED == 6
    assert result == ["p7", "p6", "p5", "p4", "p3", "p2"]
