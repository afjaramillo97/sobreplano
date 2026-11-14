"""Deterministic checks of one advisor turn: pure functions over a TurnTrace, no LLM."""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sobreplano.domain.advisor import LlmCall, ToolCallRecord
from sobreplano.evals.advisor.cases import ArgExpectation, TurnExpectation
from sobreplano.evals.language import detect_language
from sobreplano.evals.numbers import all_numbers, find_figures

TOLERANCE = Decimal("0.005")  # 0.5 % of the source value
# Tools whose results carry project prices and source URLs.
PROJECT_TOOLS = frozenset({"search_projects", "get_project", "compare_projects"})
_URL = re.compile(r"https?://[^\s\"'<>)\]]+")


@dataclass(frozen=True)
class TurnTrace:
    """What happened in one turn: the message, the answer, tool calls and LLM calls."""

    message: str
    answer: str
    tool_calls: list[ToolCallRecord]
    llm_calls: list[LlmCall]
    error: str | None = None  # AdvisorLimitError or AdvisorUnavailableError, as text


@dataclass(frozen=True)
class CheckResult:
    """One check's outcome; detail says what failed, or what was checked."""

    name: str
    passed: bool
    detail: str = ""


def normalize(text: str) -> str:
    """Lowercase without accents, for comparisons that ignore both."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in plain if not unicodedata.combining(c))


def check_completed(turn: TurnTrace) -> CheckResult:
    """Passes if the turn ended without an advisor error and with a non-empty answer."""
    if turn.error is not None:
        return CheckResult("completed", False, turn.error)
    if not turn.answer.strip():
        return CheckResult("completed", False, "empty answer")
    return CheckResult("completed", True)


def check_tools(expect: TurnExpectation, turn: TurnTrace) -> CheckResult:
    """Required tools all appear (in order if tools_ordered) and no forbidden one does.

    An entry "a|b" is met by a call to either; entries with fewer alternatives are matched
    first, so a call is not spent on a flexible entry that a strict one needed.
    """
    called = [call.name for call in turn.tool_calls]
    problems: list[str] = []
    missing = _missing_tools(expect.tools_required, called)
    if missing:
        problems.append(f"missing {missing}")
    elif expect.tools_ordered and not _is_subsequence(expect.tools_required, called):
        problems.append(f"expected order {expect.tools_required}")
    forbidden = sorted({name for name in called if name in expect.tools_forbidden})
    if forbidden:
        problems.append(f"forbidden {forbidden}")
    detail = "; ".join(problems) + f" (called {called})" if problems else f"called {called}"
    return CheckResult("tools", not problems, detail)


def check_tool_args(expect: TurnExpectation, turn: TurnTrace) -> CheckResult:
    """For each tool with expectations, at least one of its calls meets all of them."""
    problems: list[str] = []
    for tool, expectations in expect.tool_args.items():
        calls = [call.args for call in turn.tool_calls if call.name == tool]
        if not any(_args_match(args, expectations) for args in calls):
            problems.append(f"{tool}: no call meets {_describe(expectations)}; calls {calls}")
    return CheckResult("tool_args", not problems, "; ".join(problems))


def check_mentions(expect: TurnExpectation, turn: TurnTrace) -> CheckResult:
    """Every must_mention appears and no must_not_mention does, ignoring accents and case."""
    answer = normalize(turn.answer)
    missing = [text for text in expect.must_mention if normalize(text) not in answer]
    present = [text for text in expect.must_not_mention if normalize(text) in answer]
    problems: list[str] = []
    if missing:
        problems.append(f"missing {missing}")
    if present:
        problems.append(f"should not mention {present}")
    return CheckResult("mentions", not problems, "; ".join(problems))


def check_grounded(
    turn: TurnTrace, history: Sequence[TurnTrace], known: Sequence[Decimal] = ()
) -> CheckResult:
    """Every COP amount and percentage of the answer is, within 0.5 %, in a source.

    Sources: user messages, tool call arguments and tool results of the conversation so
    far, and `known`, the numbers in the tool definitions the model was given (defaults
    and limits such as the 30 % down payment or the 30-year term).
    """
    sources = [*_source_numbers([*history, turn]), *known]
    ungrounded = [f.raw for f in find_figures(turn.answer) if not _near_any(f.value, sources)]
    if ungrounded:
        return CheckResult("grounded", False, f"figures with no source: {ungrounded}")
    return CheckResult("grounded", True)


def check_cites_source(turn: TurnTrace, history: Sequence[TurnTrace]) -> CheckResult | None:
    """If the answer gives a project price, it also gives a source_url from the tool results.

    Returns None when the answer gives no project price: the check does not apply.
    """
    project_outputs = [
        call.output for t in [*history, turn] for call in t.tool_calls if call.name in PROJECT_TOOLS
    ]
    prices = [n for output in project_outputs for n in all_numbers(output)]
    quoted = [
        f for f in find_figures(turn.answer) if f.kind == "amount" and _near_any(f.value, prices)
    ]
    if not quoted:
        return None
    urls = {url.rstrip(".,") for output in project_outputs for url in _URL.findall(output)}
    if any(url in turn.answer for url in urls):
        return CheckResult("cites_source", True)
    return CheckResult(
        "cites_source", False, f"prices {[f.raw for f in quoted]} without a source_url"
    )


def check_language(expect: TurnExpectation, turn: TurnTrace) -> CheckResult:
    """The detected language of the answer is the expected one."""
    detected = detect_language(turn.answer)
    return CheckResult(
        "language", detected == expect.language, f"expected {expect.language}, got {detected}"
    )


def run_checks(
    expect: TurnExpectation,
    turn: TurnTrace,
    history: Sequence[TurnTrace],
    known: Sequence[Decimal] = (),
) -> list[CheckResult]:
    """All checks that apply to the turn; history holds the earlier turns of the conversation.

    known: numbers of the tool definitions, an extra source for `grounded`.

    A turn that did not complete only reports `completed`: the other checks would judge an
    answer that does not exist.
    """
    completed = check_completed(turn)
    if not completed.passed:
        return [completed]
    results = [completed]
    if expect.tools_required or expect.tools_forbidden:
        results.append(check_tools(expect, turn))
    if expect.tool_args:
        results.append(check_tool_args(expect, turn))
    if expect.must_mention or expect.must_not_mention:
        results.append(check_mentions(expect, turn))
    results.append(check_grounded(turn, history, known))
    cites = check_cites_source(turn, history)
    if cites is not None:
        results.append(cites)
    results.append(check_language(expect, turn))
    return results


def arg_matches(expectation: ArgExpectation, value: object) -> bool:
    """Whether one argument value meets every condition that is set."""
    if expectation.eq is not None and not _equal(expectation.eq, value):
        return False
    number = _as_number(value)
    if expectation.lte is not None and (number is None or number > expectation.lte):
        return False
    if expectation.gte is not None and (number is None or number < expectation.gte):
        return False
    return expectation.contains is None or _contains(value, expectation.contains)


def _args_match(args: dict[str, object], expectations: dict[str, ArgExpectation]) -> bool:
    return all(
        name in args and arg_matches(expectation, args[name])
        for name, expectation in expectations.items()
    )


def _equal(expected: object, value: object) -> bool:
    if isinstance(expected, str):
        return isinstance(value, str) and normalize(value) == normalize(expected)
    expected_number, number = _as_number(expected), _as_number(value)
    if expected_number is not None:
        return number is not None and number == expected_number
    return expected == value


def _as_number(value: object) -> float | None:
    # bool is an int subclass, but True is never a price or a rate.
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _contains(value: object, items: list[str]) -> bool:
    if isinstance(value, str):
        return all(normalize(item) in normalize(value) for item in items)
    if isinstance(value, list):
        present = {normalize(v) for v in value if isinstance(v, str)}  # pyright: ignore[reportUnknownVariableType]
        return all(normalize(item) in present for item in items)
    return False


def _describe(expectations: dict[str, ArgExpectation]) -> str:
    return ", ".join(
        f"{name} {expectation.model_dump(exclude_none=True)}"
        for name, expectation in expectations.items()
    )


def tool_alternatives(requirement: str) -> list[str]:
    """The tools that satisfy one tools_required entry: "a|b" accepts a or b."""
    return requirement.split("|")


def _missing_tools(required: list[str], called: list[str]) -> list[str]:
    """Required entries with no call left to satisfy them; each call satisfies one entry."""
    remaining = Counter(called)
    missing: list[str] = []
    for requirement in sorted(required, key=lambda r: len(tool_alternatives(r))):
        chosen = next((n for n in tool_alternatives(requirement) if remaining[n] > 0), None)
        if chosen is None:
            missing.append(requirement)
        else:
            remaining[chosen] -= 1
    return sorted(missing)


def _is_subsequence(wanted: list[str], called: list[str]) -> bool:
    remaining = iter(called)
    return all(any(name in tool_alternatives(w) for name in remaining) for w in wanted)


def _source_numbers(turns: Sequence[TurnTrace]) -> list[Decimal]:
    calls = [call for t in turns for call in t.tool_calls]
    texts = [t.message for t in turns] + [call.output for call in calls]
    numbers = [number for text in texts for number in all_numbers(text)]
    # Arguments the advisor sent, such as down_payment_pct=20, are what the tool computed with.
    numbers += [
        Decimal(str(value))
        for call in calls
        for value in call.args.values()
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]
    return numbers


def _near_any(value: Decimal, sources: Sequence[Decimal]) -> bool:
    return any(abs(value - source) <= abs(source) * TOLERANCE for source in sources)
