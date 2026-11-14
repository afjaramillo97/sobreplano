"""Judge calibration: export blind pairs to label, then measure agreement and Cohen's kappa."""

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from sobreplano.evals.advisor.cases import RubricId
from sobreplano.evals.advisor.judge import rubric_texts
from sobreplano.evals.advisor.runner import AdvisorRunReport
from sobreplano.infrastructure.llm.prompt_store import Prompt

TO_LABEL_PATH = Path("evals/advisor/to_label.jsonl")
LABELS_PATH = Path("evals/advisor/labels.jsonl")
CALIBRATION_PATH = Path("evals/advisor/calibration.json")

MIN_AGREEMENT = 0.85
MIN_KAPPA = 0.6
MIN_LABELS_PER_RUBRIC = 5


class LabelItem(BaseModel):
    """One (turn, rubric) pair to label blind: everything the judge saw, never its verdict."""

    model_config = ConfigDict(extra="forbid")

    key: str
    rubric: RubricId
    rubric_text: str
    user_messages: list[str]
    tool_results: list[str]
    answer: str
    human_passed: bool | None = None  # filled by hand
    note: str = ""


class RubricAgreement(BaseModel):
    """Judge against human on one rubric: agreement, kappa and the confusion matrix."""

    rubric: RubricId
    labels: int
    agreement: float
    kappa: float | None  # None when it is undefined (both raters always gave one value)
    both_pass: int
    judge_pass_human_fail: int
    judge_fail_human_pass: int
    both_fail: int

    @property
    def calibrated(self) -> bool:
        """Enough labels, agreement and kappa for the rubric to block CI."""
        return (
            self.labels >= MIN_LABELS_PER_RUBRIC
            and self.agreement >= MIN_AGREEMENT
            and self.kappa is not None
            and self.kappa >= MIN_KAPPA
        )


class CalibrationState(BaseModel):
    """evals/advisor/calibration.json: valid only for the judge prompt version it names."""

    judge_model: str
    judge_prompt_version: str
    report: str
    rubrics: list[RubricAgreement]

    def calibrated(self) -> list[RubricId]:
        """Rubrics that passed calibration."""
        return [r.rubric for r in self.rubrics if r.calibrated]


def label_key(case_id: str, run: int, turn: int, rubric: str) -> str:
    """Stable id of one judged pair inside a report."""
    return f"{case_id}/r{run}/t{turn}/{rubric}"


def export_for_labeling(report: AdvisorRunReport, prompt: Prompt) -> list[LabelItem]:
    """Every judged (turn, rubric) pair of the report, without the judge's verdict."""
    _, texts = rubric_texts(prompt)
    items: list[LabelItem] = []
    for run in report.runs:
        user_messages: list[str] = []
        for turn in run.turns:
            user_messages.append(turn.trace.message)
            for result in turn.rubrics:
                items.append(
                    LabelItem(
                        key=label_key(run.case_id, run.run, turn.turn, result.rubric),
                        rubric=result.rubric,
                        rubric_text=texts[result.rubric],
                        user_messages=list(user_messages),
                        tool_results=[call.output for call in turn.trace.tool_calls],
                        answer=turn.trace.answer,
                    )
                )
    return items


def write_jsonl(path: Path, items: Iterable[BaseModel]) -> int:
    """Write one JSON object per line and return how many were written."""
    lines = [item.model_dump_json() for item in items]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return len(lines)


def load_labels(path: Path = LABELS_PATH) -> dict[str, bool]:
    """Human labels by key; items still without human_passed are skipped.

    Raises:
        FileNotFoundError: if path does not exist.
        pydantic.ValidationError: if a line is not a LabelItem.
    """
    labels: dict[str, bool] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = LabelItem.model_validate_json(line)
            if item.human_passed is not None:
                labels[item.key] = item.human_passed
    return labels


def cohen_kappa(pairs: Sequence[tuple[bool, bool]]) -> float | None:
    """Cohen's kappa of (judge, human) pairs; None if chance agreement is 1 (undefined)."""
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(judge == human for judge, human in pairs) / n
    judge_pass = sum(judge for judge, _ in pairs) / n
    human_pass = sum(human for _, human in pairs) / n
    expected = judge_pass * human_pass + (1 - judge_pass) * (1 - human_pass)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def score(report: AdvisorRunReport, labels: dict[str, bool]) -> list[RubricAgreement]:
    """Agreement per rubric between the report's verdicts and the human labels.

    Pairs without a label, or whose judge call failed, are left out.
    """
    pairs: dict[RubricId, list[tuple[bool, bool]]] = {}
    for run in report.runs:
        for turn in run.turns:
            for result in turn.rubrics:
                key = label_key(run.case_id, run.run, turn.turn, result.rubric)
                if result.passed is not None and key in labels:
                    pairs.setdefault(result.rubric, []).append((result.passed, labels[key]))
    return [_agreement(rubric, rubric_pairs) for rubric, rubric_pairs in sorted(pairs.items())]


def _agreement(rubric: RubricId, pairs: list[tuple[bool, bool]]) -> RubricAgreement:
    return RubricAgreement(
        rubric=rubric,
        labels=len(pairs),
        agreement=sum(judge == human for judge, human in pairs) / len(pairs),
        kappa=cohen_kappa(pairs),
        both_pass=sum(judge and human for judge, human in pairs),
        judge_pass_human_fail=sum(judge and not human for judge, human in pairs),
        judge_fail_human_pass=sum(not judge and human for judge, human in pairs),
        both_fail=sum(not judge and not human for judge, human in pairs),
    )


def load_calibration(path: Path = CALIBRATION_PATH) -> CalibrationState | None:
    """The saved calibration, or None if there is none yet."""
    if not path.exists():
        return None
    return CalibrationState.model_validate_json(path.read_text(encoding="utf-8"))


def calibrated_rubrics(state: CalibrationState | None, prompt_version: str) -> frozenset[str]:
    """Rubrics that may block: calibrated with this exact judge prompt, else none."""
    if state is None or state.judge_prompt_version != prompt_version:
        return frozenset()
    return frozenset(state.calibrated())


def to_markdown(agreements: Sequence[RubricAgreement]) -> str:
    """Table of agreement, kappa and confusion matrix per rubric."""
    lines = [
        "| Rubric | Labels | Agreement | Kappa | J✓H✓ | J✓H✗ | J✗H✓ | J✗H✗ | Calibrated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for a in agreements:
        kappa = "n/a" if a.kappa is None else f"{a.kappa:.2f}"
        lines.append(
            f"| {a.rubric} | {a.labels} | {a.agreement:.0%} | {kappa} | {a.both_pass} "
            f"| {a.judge_pass_human_fail} | {a.judge_fail_human_pass} | {a.both_fail} "
            f"| {'yes' if a.calibrated else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def save_calibration(state: CalibrationState, path: Path = CALIBRATION_PATH) -> None:
    """Write calibration.json, pretty-printed so its diff reads well in a PR."""
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
