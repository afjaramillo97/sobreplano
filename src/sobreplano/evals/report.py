"""Pieces shared by eval reports: token and cost totals, the cost cap and the report files."""

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sobreplano.domain.advisor import LlmCall
from sobreplano.infrastructure.llm.providers import MODEL_PRICES_USD_PER_MILLION

REPORTS_DIR = Path("evals/reports")


class UnknownPriceError(Exception):
    """A model has no price in the table, so the cost cap could not be enforced."""


@dataclass
class UsageTotals:
    """Calls, tokens and estimated cost of a group of LLM calls (constitution, principle 5)."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    unpriced_calls: int = 0  # calls of a model without a price, not in cost_usd

    def add(self, calls: Iterable[LlmCall]) -> None:
        """Add calls to the totals."""
        for call in calls:
            self.calls += 1
            self.input_tokens += call.input_tokens
            self.output_tokens += call.output_tokens
            if call.cost_usd is None:
                self.unpriced_calls += 1
            else:
                self.cost_usd += call.cost_usd

    def to_json(self) -> dict[str, object]:
        """Plain values for the JSON report."""
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": str(self.cost_usd),
            "unpriced_calls": self.unpriced_calls,
        }


@dataclass
class CostCap:
    """Stops a run once its estimated cost passes max_cost_usd.

    The check happens between cases, so a run can end slightly above the cap.
    """

    max_cost_usd: Decimal
    spent_usd: Decimal = Decimal(0)

    def add(self, calls: Iterable[LlmCall]) -> None:
        """Count the cost of calls; unpriced calls count as zero."""
        self.spent_usd += sum((c.cost_usd for c in calls if c.cost_usd is not None), Decimal(0))

    @property
    def exceeded(self) -> bool:
        """Whether the spend so far is over the cap."""
        return self.spent_usd > self.max_cost_usd


def require_prices(models: Iterable[str], *, allow_unknown: bool) -> None:
    """Make sure every model has a price, unless the caller accepts an unbounded cost.

    Raises:
        UnknownPriceError: if a model is missing from MODEL_PRICES_USD_PER_MILLION and
            allow_unknown is false.
    """
    unknown = sorted({m for m in models if m not in MODEL_PRICES_USD_PER_MILLION})
    if unknown and not allow_unknown:
        raise UnknownPriceError(
            f"no price for {unknown}: add it to MODEL_PRICES_USD_PER_MILLION "
            "or pass --allow-unknown-cost"
        )


def git_commit() -> str | None:
    """The current commit (with "-dirty" if there are local changes), or None outside git."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return f"{commit}-dirty" if dirty else commit


def report_stem(kind: str, model: str, day: date) -> str:
    """File name without extension, e.g. advisor-2026-11-13-openai_gpt-6-luna."""
    return f"{kind}-{day.isoformat()}-{re.sub(r'[^A-Za-z0-9.-]+', '_', model)}"


def write_report(stem: str, data: str, markdown: str, directory: Path = REPORTS_DIR) -> Path:
    """Write <stem>.json and <stem>.md into directory and return the JSON path."""
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    json_path.write_text(data, encoding="utf-8")
    (directory / f"{stem}.md").write_text(markdown, encoding="utf-8")
    return json_path


def percent(passed: int, total: int) -> str:
    """A pass rate for the Markdown report, "n/a" when nothing was evaluated."""
    return f"{100 * passed / total:.1f} %" if total else "n/a"
