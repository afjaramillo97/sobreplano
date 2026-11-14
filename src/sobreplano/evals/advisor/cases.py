"""Schema of evals/advisor/cases.json: conversations and what each turn must do."""

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CASES_PATH = Path("evals/advisor/cases.json")

RubricId = Literal[
    "helpful", "price_citation", "simulation_caveat", "asks_rate", "scope", "privacy"
]
Category = Literal["search", "history", "compare", "finance", "scope", "memory"]


class _Strict(BaseModel):
    """Unknown fields are typos in the case file, so they are errors."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ArgExpectation(_Strict):
    """What one tool argument must satisfy; every field that is set must hold.

    Strings compare without accents or case; `contains` checks items of a list or
    substrings of a string.
    """

    eq: object | None = None
    lte: float | None = None
    gte: float | None = None
    contains: list[str] | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if self.eq is None and self.lte is None and self.gte is None and self.contains is None:
            raise ValueError("an argument expectation needs eq, lte, gte or contains")
        return self


class TurnExpectation(_Strict):
    """What a turn must do; each deterministic check runs only when its fields are set."""

    tools_required: list[str] = []  # all must appear, repeats included
    tools_ordered: bool = False  # in this relative order
    tools_forbidden: list[str] = []
    tool_args: dict[str, dict[str, ArgExpectation]] = {}  # one call of that tool meets all
    must_mention: list[str] = []  # compared without accents or case
    must_not_mention: list[str] = []
    language: Literal["es", "en"] = "es"
    rubrics: list[RubricId] = []  # judged by the LLM judge (price_citation is added by code)


class Turn(_Strict):
    """One user message and its expectation."""

    message: Annotated[str, Field(min_length=1)]
    expect: TurnExpectation


class EvalCase(_Strict):
    """A conversation: its turns share one thread_id."""

    id: Annotated[str, Field(pattern=r"^[A-Z]\d+$")]
    category: Category
    description: str
    turns: Annotated[list[Turn], Field(min_length=1)]


class CaseFile(_Strict):
    """The whole case file."""

    cases: list[EvalCase]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate case ids")
        return self


def load_cases(path: Path = CASES_PATH) -> list[EvalCase]:
    """Read and validate the case file.

    Raises:
        FileNotFoundError: if path does not exist.
        pydantic.ValidationError: if a case breaks the schema.
    """
    return CaseFile.model_validate_json(path.read_text(encoding="utf-8")).cases
