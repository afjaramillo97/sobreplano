"""Runs an extractor over the golden set and builds the report: quality, cost and latency."""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel

from sobreplano.domain.advisor import LlmCall
from sobreplano.domain.errors import ExtractionError
from sobreplano.domain.ports import ProjectPageExtractor
from sobreplano.domain.scraping import normalize_unit_type_name
from sobreplano.evals.extraction.golden import ExtractionLabel
from sobreplano.evals.extraction.metrics import Metrics, PageScore, score_page, total
from sobreplano.evals.report import CostCap, UsageTotals
from sobreplano.infrastructure.llm.providers import estimate_cost_usd

_COST_QUANTUM = Decimal("0.000001")


class PageRun(BaseModel):
    """One extraction of one golden page."""

    run: int  # 1-based, up to --repeat
    seconds: float
    call: LlmCall | None  # None when the call failed before any usage came back
    score: PageScore


class ExtractionRunReport(BaseModel):
    """One evals run of one extraction model."""

    model: str
    prompt_version: str
    commit: str | None
    started_at: datetime
    finished_at: datetime
    repeat: int
    max_cost_usd: Decimal
    case_ids: list[str]
    complete: bool
    stop_reason: str | None
    pages: list[PageRun]
    usage: UsageTotals

    def metrics(self) -> Metrics:
        """Totals over every page of every run."""
        return total([page.score for page in self.pages])

    def renamed_between_runs(self) -> list[str]:
        """Unit types the model named differently in different runs of the same page.

        A new name for the same unit type would split its price history, so this is worth
        watching even though it has no threshold. Needs at least two runs.
        """
        names: dict[tuple[str, str], dict[str, str]] = {}
        for page in self.pages:
            for label_name, given in page.score.pairing.items():
                seen = names.setdefault((page.score.case_id, label_name), {})
                seen.setdefault(normalize_unit_type_name(given), given)
        return [
            f"{case_id}: {label_name!r} named {' / '.join(repr(n) for n in seen.values())}"
            for (case_id, label_name), seen in names.items()
            if len(seen) > 1
        ]

    def failures(self) -> list[str]:
        """Why the run fails: incomplete, or a threshold the model misses as the extractor."""
        reasons = [] if self.complete else [f"incomplete: {self.stop_reason}"]
        return reasons + self.metrics().eligibility_failures()

    def to_markdown(self) -> str:
        """Human summary: metrics against thresholds, failed pages, cost and latency."""
        m = self.metrics()
        seconds = [page.seconds for page in self.pages]
        lines = [
            f"# Extraction evals: {self.model}",
            "",
            f"- Commit: `{self.commit}` · extractor prompt `{self.prompt_version}`",
            f"- {len(self.case_ids)} pages, {self.repeat} runs each, "
            f"started {self.started_at:%Y-%m-%d %H:%M} UTC",
            f"- Eligible as extractor: **{'no' if self.failures() else 'yes'}**",
        ]
        lines += [f"  - {reason}" for reason in self.failures()]
        lines += [
            "",
            "## Metrics",
            "",
            "| Metric | Value | Threshold |",
            "| --- | --- | --- |",
            f"| Price accuracy | {m.price_accuracy:.1%} ({m.prices_ok}/{m.matched}) | ≥ 98% |",
            f"| Unit type recall | {m.type_recall:.1%} ({m.matched}/{m.expected}) | ≥ 95% |",
            f"| Unit type precision | {m.type_precision:.1%} ({m.matched}/{m.found}) | |",
            f"| Field accuracy | {m.field_accuracy:.1%} | ≥ 95% |",
            f"| Unit type name exact (of matched) | {m.name_accuracy:.1%} "
            f"({m.names_exact}/{m.matched}) | |",
            f"| Project name and neighborhood | {m.project_accuracy:.1%} | |",
            f"| Perfect pages | {m.perfect_pages}/{m.pages} | |",
            f"| Extraction errors | {m.errors} | |",
            "",
            "## Pages with problems",
            "",
        ]
        flawed = [page for page in self.pages if not page.score.perfect]
        if not flawed:
            lines.append("None.")
        for page in flawed:
            lines.append(f"- **{page.score.case_id}** run {page.run}")
            if page.score.error:
                lines.append(f"  - error: {page.score.error}")
            lines += [f"  - {problem}" for problem in page.score.problems]
        if self.repeat >= 2:
            renamed = self.renamed_between_runs()
            lines += ["", f"## Unit types renamed between runs: {len(renamed)}", ""]
            lines += [f"- {entry}" for entry in renamed] or ["None."]
        lines += [
            "",
            "## Cost and latency",
            "",
            f"- {self.usage.calls} calls, {self.usage.input_tokens} input and "
            f"{self.usage.output_tokens} output tokens, {self.usage.cost_usd:.4f} USD",
        ]
        if seconds:
            lines.append(f"- {sum(seconds) / len(seconds):.1f} s per page on average")
        return "\n".join(lines) + "\n"


def run_extraction_evals(
    labels: Sequence[ExtractionLabel],
    texts: dict[str, str],
    extractor: ProjectPageExtractor,
    *,
    commit: str | None,
    repeat: int,
    cost_cap: CostCap,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ExtractionRunReport:
    """Extract every page `repeat` times, stopping before the next page once the cap is passed.

    Raises:
        ValueError: if a label is not reviewed or has no text: unreviewed labels would
            only measure the model against its own earlier answers.
    """
    unreviewed = [label.case_id for label in labels if not label.reviewed]
    if unreviewed:
        raise ValueError(f"labels not reviewed yet: {unreviewed}")
    missing = [label.case_id for label in labels if label.case_id not in texts]
    if missing:
        raise ValueError(f"labels without text: {missing}")

    started_at = now()
    pages: list[PageRun] = []
    usage = UsageTotals()
    stop_reason: str | None = None
    for run in range(1, repeat + 1):
        for label in labels:
            if cost_cap.exceeded:
                stop_reason = (
                    f"cost {cost_cap.spent_usd:.4f} USD passed --max-cost "
                    f"{cost_cap.max_cost_usd} before {label.case_id} run {run}"
                )
                break
            page = _extract(extractor, label, texts[label.case_id], run)
            if page.call is not None:
                usage.add([page.call])
                cost_cap.add([page.call])
            pages.append(page)
        if stop_reason is not None:
            break
    return ExtractionRunReport(
        model=extractor.model,
        prompt_version=extractor.prompt_version,
        commit=commit,
        started_at=started_at,
        finished_at=now(),
        repeat=repeat,
        max_cost_usd=cost_cap.max_cost_usd,
        case_ids=[label.case_id for label in labels],
        complete=stop_reason is None,
        stop_reason=stop_reason,
        pages=pages,
        usage=usage,
    )


def _extract(
    extractor: ProjectPageExtractor, label: ExtractionLabel, text: str, run: int
) -> PageRun:
    started = time.monotonic()
    try:
        result = extractor.extract(text)
    except ExtractionError as error:
        # A failed page counts as one that found nothing; its tokens are unknown.
        seconds = time.monotonic() - started
        return PageRun(
            run=run, seconds=seconds, call=None, score=score_page(label, None, str(error))
        )
    seconds = time.monotonic() - started
    cost = estimate_cost_usd(result.model, result.input_tokens, result.output_tokens)
    call = LlmCall(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=None if cost is None else Decimal(str(cost)).quantize(_COST_QUANTUM),
        prompt_version=result.prompt_version,
    )
    return PageRun(run=run, seconds=seconds, call=call, score=score_page(label, result.project))
