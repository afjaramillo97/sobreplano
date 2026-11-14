"""Runs the advisor cases against a real AdvisorAgent and builds the report with its thresholds."""

import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import BaseModel

from sobreplano.domain.errors import AdvisorLimitError, AdvisorUnavailableError
from sobreplano.domain.ports import AdvisorAgent
from sobreplano.evals.advisor.cases import Category, EvalCase
from sobreplano.evals.advisor.checks import CheckResult, TurnTrace, run_checks
from sobreplano.evals.report import CostCap, UsageTotals, percent

# "Never" rules must always hold; every other deterministic check at 90 %.
CHECK_THRESHOLDS = {"grounded": 1.0}
DEFAULT_CHECK_THRESHOLD = 0.9


class TurnResult(BaseModel):
    """One turn of one case run: what happened and how the checks judged it."""

    turn: int  # 1-based
    trace: TurnTrace
    checks: list[CheckResult]
    seconds: float

    @property
    def passed(self) -> bool:
        """Whether every check of the turn passed."""
        return all(check.passed for check in self.checks)


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
    """Pass count of one check over every turn where it was evaluated."""

    name: str
    passed: int
    total: int
    threshold: float

    @property
    def ok(self) -> bool:
        """Whether the rate meets the threshold; a check never evaluated does not fail."""
        return self.total == 0 or self.passed / self.total >= self.threshold


class AdvisorRunReport(BaseModel):
    """Everything about one evals run, saved as JSON and summarized as Markdown."""

    model: str
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
            for rate in self.check_rates()
            if not rate.ok
        ]
        return reasons

    def to_markdown(self) -> str:
        """Human summary: rates against thresholds, consistency, failed turns and cost."""
        consistent, inconsistent = self.consistency()
        lines = [
            f"# Advisor evals: {self.model}",
            "",
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
        failed = [(run, turn) for run in self.runs for turn in run.turns if not turn.passed]
        if not failed:
            lines.append("None.")
        for run, turn in failed:
            lines.append(
                f"- **{run.case_id}** run {run.run} turn {turn.turn}: {turn.trace.message}"
            )
            lines += [f"  - `{c.name}`: {c.detail}" for c in turn.checks if not c.passed]
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


def run_case(advisor: AdvisorAgent, case: EvalCase, run: int) -> CaseRun:
    """Play every turn of case in a new thread and check each one."""
    thread_id = uuid4()
    history: list[TurnTrace] = []
    results: list[TurnResult] = []
    for number, turn in enumerate(case.turns, start=1):
        started = time.monotonic()
        trace = _play(advisor, thread_id, turn.message)
        seconds = time.monotonic() - started
        checks = run_checks(turn.expect, trace, history)
        results.append(TurnResult(turn=number, trace=trace, checks=checks, seconds=seconds))
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
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AdvisorRunReport:
    """Run every case `repeat` times, stopping before the next case once the cap is passed."""
    started_at = now()
    runs: list[CaseRun] = []
    usage = UsageTotals()
    stop_reason: str | None = None
    for run in range(1, repeat + 1):
        for case in cases:
            if cost_cap.exceeded:
                stop_reason = (
                    f"cost {cost_cap.spent_usd:.4f} USD passed --max-cost "
                    f"{cost_cap.max_cost_usd} before {case.id} run {run}"
                )
                break
            case_run = run_case(advisor, case, run)
            calls = [call for turn in case_run.turns for call in turn.trace.llm_calls]
            usage.add(calls)
            cost_cap.add(calls)
            runs.append(case_run)
        if stop_reason is not None:
            break
    return AdvisorRunReport(
        model=model,
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
        judge_usage=UsageTotals(),
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
