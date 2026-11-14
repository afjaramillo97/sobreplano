"""Runs the advisor cases against a real AdvisorAgent and builds the report with its thresholds."""

import json
import re
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from sobreplano.domain.advisor import LlmCall
from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.domain.ports import AdvisorAgent
from sobreplano.evals.advisor.cases import Category, EvalCase, RubricId, TurnExpectation
from sobreplano.evals.advisor.checks import CheckResult, TurnTrace, run_checks
from sobreplano.evals.advisor.judge import Judge, JudgeInput, rubrics_for
from sobreplano.evals.numbers import all_numbers
from sobreplano.evals.report import CostCap, UsageTotals, percent

# "Never" rules must always hold; every other deterministic check at 90 %.
CHECK_THRESHOLDS = {"grounded": 1.0}
DEFAULT_CHECK_THRESHOLD = 0.9
# Only calibrated rubrics block; privacy is a "never" rule too.
RUBRIC_THRESHOLDS = {"privacy": 1.0}
DEFAULT_RUBRIC_THRESHOLD = 0.85


class TurnTracer(Protocol):
    """Where a turn's trace goes (Langfuse) and where its check and rubric scores land."""

    def turn(
        self, *, case_id: str, run: int, turn: int, message: str, session_id: str
    ) -> AbstractContextManager[str | None]:
        """Context for one turn; yields its trace id, or None when nothing is traced."""
        ...

    def score(self, trace_id: str | None, name: str, passed: bool, comment: str) -> None:
        """Attach one boolean score to the turn's trace."""
        ...


class RubricResult(BaseModel):
    """The judge's verdict on one rubric of one turn, or the error that prevented it."""

    rubric: RubricId
    passed: bool | None  # None when the judge call failed
    reason: str
    error: str | None = None
    blocking: bool  # calibrated with the current judge prompt
    call: LlmCall | None = None


class TurnResult(BaseModel):
    """One turn of one case run: what happened and how the checks judged it."""

    turn: int  # 1-based
    trace: TurnTrace
    checks: list[CheckResult]
    seconds: float
    rubrics: list[RubricResult] = []
    trace_id: str | None = None  # Langfuse trace of the turn, when tracing was on

    @property
    def passed(self) -> bool:
        """Whether every check and every blocking rubric of the turn passed."""
        return all(check.passed for check in self.checks) and all(
            r.passed is not False for r in self.rubrics if r.blocking
        )


class CaseRun(BaseModel):
    """One run of one case, in its own thread."""

    case_id: str
    category: Category
    run: int  # 1-based, up to --repeat
    thread_id: str
    turns: list[TurnResult]

    @property
    def passed(self) -> bool:
        """Whether every turn passed."""
        return all(turn.passed for turn in self.turns)


class Rate(BaseModel):
    """Pass count of one check or rubric over every turn where it was evaluated."""

    name: str
    passed: int
    total: int
    threshold: float
    blocking: bool = True  # False for a rubric that is not calibrated: reported only
    errors: int = 0  # judge calls that gave no verdict, not in total

    @property
    def ok(self) -> bool:
        """Whether the rate meets the threshold; a non-blocking or empty rate never fails."""
        return not self.blocking or self.total == 0 or self.passed / self.total >= self.threshold


class AdvisorRunReport(BaseModel):
    """Everything about one evals run, saved as JSON and summarized as Markdown."""

    run_id: str = ""  # also a Langfuse tag of every trace of the run
    model: str
    # Defaults so reports from before the judge (SPEC 09, step 7) still load.
    judge_model: str | None = None
    calibrated_rubrics: list[str] = []
    prompt_versions: dict[str, str]
    commit: str | None
    started_at: datetime
    finished_at: datetime
    repeat: int
    max_cost_usd: Decimal
    case_ids: list[str]
    complete: bool
    stop_reason: str | None
    runs: list[CaseRun]
    advisor_usage: UsageTotals
    judge_usage: UsageTotals

    def check_rates(self) -> list[Rate]:
        """Pass rate of each deterministic check, in order of first appearance."""
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for run in self.runs:
            for turn in run.turns:
                for check in turn.checks:
                    counts[check.name][0] += check.passed
                    counts[check.name][1] += 1
        return [
            Rate(
                name=name,
                passed=passed,
                total=total,
                threshold=CHECK_THRESHOLDS.get(name, DEFAULT_CHECK_THRESHOLD),
            )
            for name, (passed, total) in counts.items()
        ]

    def rubric_rates(self) -> list[Rate]:
        """Pass rate of each rubric; only calibrated ones carry a blocking threshold."""
        counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for run in self.runs:
            for turn in run.turns:
                for result in turn.rubrics:
                    if result.passed is None:
                        counts[result.rubric][2] += 1
                    else:
                        counts[result.rubric][0] += result.passed
                        counts[result.rubric][1] += 1
        return [
            Rate(
                name=name,
                passed=passed,
                total=total,
                threshold=RUBRIC_THRESHOLDS.get(name, DEFAULT_RUBRIC_THRESHOLD),
                blocking=name in self.calibrated_rubrics,
                errors=errors,
            )
            for name, (passed, total, errors) in sorted(counts.items())
        ]

    def consistency(self) -> tuple[list[str], list[str]]:
        """Cases that passed in every one of their runs, and cases that failed at least once."""
        passed: dict[str, bool] = {}
        for run in self.runs:
            passed[run.case_id] = passed.get(run.case_id, True) and run.passed
        return (
            [case for case, ok in passed.items() if ok],
            [case for case, ok in passed.items() if not ok],
        )

    def failures(self) -> list[str]:
        """Why the run fails: an incomplete run or each threshold that was not met."""
        reasons = [] if self.complete else [f"incomplete: {self.stop_reason}"]
        reasons += [
            f"{rate.name} {percent(rate.passed, rate.total)} < {rate.threshold:.0%}"
            for rate in [*self.check_rates(), *self.rubric_rates()]
            if not rate.ok
        ]
        return reasons

    def to_markdown(self) -> str:
        """Human summary: rates against thresholds, consistency, failed turns and cost."""
        consistent, inconsistent = self.consistency()
        lines = [
            f"# Advisor evals: {self.model}",
            "",
            f"- Judge: {self.judge_model or 'off'} · calibrated rubrics: "
            f"{', '.join(self.calibrated_rubrics) or 'none'}",
            f"- Commit: `{self.commit}` · prompts: "
            + ", ".join(f"{k} `{v}`" for k, v in self.prompt_versions.items()),
            f"- {len(self.case_ids)} cases, {self.repeat} runs each, "
            f"started {self.started_at:%Y-%m-%d %H:%M} UTC",
            f"- Result: **{'FAIL' if self.failures() else 'PASS'}**",
        ]
        lines += [f"  - {reason}" for reason in self.failures()]
        lines += [
            "",
            "## Checks",
            "",
            "| Check | Passed | Rate | Threshold | |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {r.name} | {r.passed}/{r.total} | {percent(r.passed, r.total)} "
            f"| {r.threshold:.0%} | {'ok' if r.ok else '**fail**'} |"
            for r in self.check_rates()
        ]
        if self.judge_model is not None:
            lines += [
                "",
                "## Rubrics (judge)",
                "",
                "| Rubric | Passed | Rate | Threshold | Judge errors | |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            lines += [
                f"| {r.name} | {r.passed}/{r.total} | {percent(r.passed, r.total)} "
                f"| {f'{r.threshold:.0%}' if r.blocking else 'not calibrated'} | {r.errors} "
                f"| {('ok' if r.ok else '**fail**') if r.blocking else 'report only'} |"
                for r in self.rubric_rates()
            ]
        lines += [
            "",
            "## Consistency",
            "",
            f"Passed in all {self.repeat} runs: "
            f"{len(consistent)}/{len(consistent) + len(inconsistent)}"
            + (f" · failed at least once: {', '.join(inconsistent)}" if inconsistent else ""),
            "",
            "## Failed turns",
            "",
        ]
        failed = [
            (run, turn)
            for run in self.runs
            for turn in run.turns
            if not turn.passed or any(r.passed is False for r in turn.rubrics)
        ]
        if not failed:
            lines.append("None.")
        for run, turn in failed:
            lines.append(
                f"- **{run.case_id}** run {run.run} turn {turn.turn}: {turn.trace.message}"
            )
            lines += [f"  - `{c.name}`: {c.detail}" for c in turn.checks if not c.passed]
            lines += [
                f"  - rubric `{r.rubric}`{'' if r.blocking else ' (report only)'}: {r.reason}"
                for r in turn.rubrics
                if r.passed is False
            ]
        lines += [
            "",
            "## Cost",
            "",
            "| | Calls | Input tokens | Output tokens | Cost (USD) |",
            "| --- | --- | --- | --- | --- |",
        ]
        for label, usage in (("Advisor", self.advisor_usage), ("Judge", self.judge_usage)):
            lines.append(
                f"| {label} | {usage.calls} | {usage.input_tokens} | {usage.output_tokens} "
                f"| {usage.cost_usd:.4f} |"
            )
        seconds = [turn.seconds for run in self.runs for turn in run.turns]
        if seconds:
            lines += ["", f"Mean turn latency: {sum(seconds) / len(seconds):.1f} s"]
        return "\n".join(lines) + "\n"


def run_case(
    advisor: AdvisorAgent,
    case: EvalCase,
    run: int,
    judge: Judge | None = None,
    calibrated: frozenset[str] = frozenset(),
    tracer: TurnTracer | None = None,
    known: Sequence[Decimal] = (),
) -> CaseRun:
    """Play every turn of case in a new thread, check each one and, with a judge, judge it.

    With a tracer, each turn is one trace whose scores are the checks and rubrics.
    """
    thread_id = uuid4()
    history: list[TurnTrace] = []
    results: list[TurnResult] = []
    for number, turn in enumerate(case.turns, start=1):
        started = time.monotonic()
        trace_id: str | None = None
        if tracer is None:
            trace = _play(advisor, thread_id, turn.message)
        else:
            with tracer.turn(
                case_id=case.id,
                run=run,
                turn=number,
                message=turn.message,
                session_id=str(thread_id),
            ) as trace_id:
                trace = _play(advisor, thread_id, turn.message)
        seconds = time.monotonic() - started
        checks = run_checks(turn.expect, trace, history, known)
        rubrics = (
            _judge_turn(judge, turn.expect, trace, history, checks, calibrated)
            if judge is not None
            else []
        )
        if tracer is not None:
            for check in checks:
                tracer.score(trace_id, f"check.{check.name}", check.passed, check.detail)
            for rubric in rubrics:
                if rubric.passed is not None:
                    tracer.score(trace_id, f"rubric.{rubric.rubric}", rubric.passed, rubric.reason)
        results.append(
            TurnResult(
                turn=number,
                trace=trace,
                checks=checks,
                seconds=seconds,
                rubrics=rubrics,
                trace_id=trace_id,
            )
        )
        history.append(trace)
    return CaseRun(
        case_id=case.id, category=case.category, run=run, thread_id=str(thread_id), turns=results
    )


def run_advisor_evals(
    cases: Sequence[EvalCase],
    advisor: AdvisorAgent,
    *,
    model: str,
    prompt_versions: dict[str, str],
    commit: str | None,
    repeat: int,
    cost_cap: CostCap,
    judge: Judge | None = None,
    calibrated: frozenset[str] = frozenset(),
    tracer: TurnTracer | None = None,
    known_numbers: Sequence[Decimal] = (),
    run_id: str = "",
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AdvisorRunReport:
    """Run every case `repeat` times, stopping before the next case once the cap is passed.

    The cap counts the advisor's and the judge's calls together.
    """
    started_at = now()
    runs: list[CaseRun] = []
    usage = UsageTotals()
    judge_usage = UsageTotals()
    stop_reason: str | None = None
    for run in range(1, repeat + 1):
        for case in cases:
            if cost_cap.exceeded:
                stop_reason = (
                    f"cost {cost_cap.spent_usd:.4f} USD passed --max-cost "
                    f"{cost_cap.max_cost_usd} before {case.id} run {run}"
                )
                break
            case_run = run_case(advisor, case, run, judge, calibrated, tracer, known_numbers)
            calls = [call for turn in case_run.turns for call in turn.trace.llm_calls]
            judge_calls = [r.call for t in case_run.turns for r in t.rubrics if r.call is not None]
            usage.add(calls)
            judge_usage.add(judge_calls)
            cost_cap.add([*calls, *judge_calls])
            runs.append(case_run)
        if stop_reason is not None:
            break
    return AdvisorRunReport(
        run_id=run_id,
        model=model,
        judge_model=None if judge is None else judge.model,
        calibrated_rubrics=sorted(calibrated) if judge is not None else [],
        prompt_versions=prompt_versions,
        commit=commit,
        started_at=started_at,
        finished_at=now(),
        repeat=repeat,
        max_cost_usd=cost_cap.max_cost_usd,
        case_ids=[case.id for case in cases],
        complete=stop_reason is None,
        stop_reason=stop_reason,
        runs=runs,
        advisor_usage=usage,
        judge_usage=judge_usage,
    )


def _play(advisor: AdvisorAgent, thread_id: UUID, message: str) -> TurnTrace:
    # A limit or provider error is a failed turn, not a crash of the run.
    try:
        reply = advisor.reply(thread_id, message)
    except AdvisorLimitError as error:
        return TurnTrace(message, "", [], list(error.llm_calls), f"AdvisorLimitError: {error}")
    except AdvisorUnavailableError as error:
        return TurnTrace(message, "", [], [], f"AdvisorUnavailableError: {error}")
    return TurnTrace(message, reply.text, reply.tool_calls, reply.llm_calls)


def _judge_turn(
    judge: Judge,
    expect: TurnExpectation,
    trace: TurnTrace,
    history: Sequence[TurnTrace],
    checks: Sequence[CheckResult],
    calibrated: frozenset[str],
) -> list[RubricResult]:
    # An answer that does not exist has nothing to judge; `completed` already failed.
    if trace.error is not None:
        return []
    cites_source = any(check.name == "cites_source" for check in checks)
    data = JudgeInput(
        user_messages=[*(t.message for t in history), trace.message],
        tool_results=[call.output for call in trace.tool_calls],
        answer=trace.answer,
    )
    results: list[RubricResult] = []
    for rubric in rubrics_for(expect.rubrics, cites_source):
        outcome = judge.judge(rubric, data)
        verdict = outcome.verdict
        results.append(
            RubricResult(
                rubric=rubric,
                passed=None if verdict is None else verdict.passed,
                reason="" if verdict is None else verdict.reason,
                error=outcome.error,
                blocking=rubric in calibrated,
                call=outcome.call,
            )
        )
    return results


# "e.g. 12 for 12 %" is an example, not a fact: an invented 12 % rate must not pass.
_EXAMPLE = re.compile(r"e\.g\.[^.]*")


def tool_definition_numbers(tools: Sequence[BaseTool]) -> list[Decimal]:
    """Numbers in what the model is told about each tool: description, defaults and limits.

    Examples ("e.g. ...") are left out.
    """
    numbers: list[Decimal] = []
    for tool in tools:
        texts = [tool.description]
        if isinstance(tool.args_schema, type) and issubclass(tool.args_schema, BaseModel):
            texts.append(json.dumps(tool.args_schema.model_json_schema()))
        numbers += [n for text in texts for n in all_numbers(_EXAMPLE.sub("", text))]
    return numbers
