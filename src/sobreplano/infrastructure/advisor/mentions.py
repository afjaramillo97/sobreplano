"""Which projects an advisor answer names, matched against the projects its tools returned."""

import re
import unicodedata
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from sobreplano.domain.advisor import ToolCallRecord
from sobreplano.infrastructure.advisor.tools import MAX_DETAILS_PER_MESSAGE

# The same cap as the details a message may fetch: more cards than that would not help.
MAX_MENTIONED = MAX_DETAILS_PER_MESSAGE


class _ProjectRef(BaseModel):
    slug: str
    name: str


class _SearchOut(BaseModel):
    projects: list[_ProjectRef] = []


class _GetOut(BaseModel):
    project: _ProjectRef | None = None


class _ComparisonRow(BaseModel):
    project_slug: str
    project_name: str


class _CompareOut(BaseModel):
    rows: list[_ComparisonRow] = []


def mentioned_projects(text: str, tool_calls: Sequence[ToolCallRecord]) -> list[str]:
    """Slugs of the projects returned by the turn's tools whose name appears in text.

    The match ignores accents and case and needs whole words. Slugs come in order of first
    mention, without repeats, at most MAX_MENTIONED. Outputs that are not valid JSON of
    search_projects, get_project or compare_projects, such as tool errors, are skipped.
    """
    names = _returned_projects(tool_calls)
    folded = _fold(text)
    claimed: list[tuple[int, int]] = []
    first_seen: dict[str, int] = {}
    # Longest names first, and their spans are claimed: "Arrayanes del Sur" in the text
    # must not also count as a mention of a project called "Arrayanes".
    for slug, name in sorted(names.items(), key=lambda item: -len(item[1])):
        pattern = rf"(?<!\w){re.escape(_fold(name))}(?!\w)"
        for match in re.finditer(pattern, folded):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in claimed):
                continue
            claimed.append(span)
            first_seen.setdefault(slug, span[0])
    ordered = sorted(first_seen, key=lambda slug: first_seen[slug])
    return ordered[:MAX_MENTIONED]


def _returned_projects(tool_calls: Sequence[ToolCallRecord]) -> dict[str, str]:
    """Slug to name of every project in the outputs of the project tools."""
    names: dict[str, str] = {}
    for call in tool_calls:
        try:
            if call.name == "search_projects":
                refs = _SearchOut.model_validate_json(call.output).projects
                names.update((ref.slug, ref.name) for ref in refs)
            elif call.name == "get_project":
                project = _GetOut.model_validate_json(call.output).project
                if project is not None:
                    names[project.slug] = project.name
            elif call.name == "compare_projects":
                rows = _CompareOut.model_validate_json(call.output).rows
                names.update((row.project_slug, row.project_name) for row in rows)
        except ValidationError:
            continue
    return {slug: name for slug, name in names.items() if name.strip()}


def _fold(text: str) -> str:
    """Lowercase without accents, so "Ciprés" in a tool result matches "cipres" in the text."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in plain if not unicodedata.combining(c))
