"""Judge calibration: labeled pairs, the judge's verdicts on them, agreement and Cohen's kappa.

A label is a whole pair (rubric, user messages, tool results, answer) with a human verdict, so
it does not depend on any report. Pairs come from reports (real) or are written to be hard
(synthetic). The judge judges every labeled pair that has no verdict from the current judge
(model and prompt version), and agreement is computed against those verdicts.
"""

import hashlib
import json
import random
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, model_validator

from sobreplano.domain.advisor import LlmCall
from sobreplano.evals.advisor.cases import RubricId
from sobreplano.evals.advisor.judge import Judge, JudgeInput, rubric_texts
from sobreplano.evals.advisor.runner import AdvisorRunReport
from sobreplano.evals.report import CostCap, UsageTotals
from sobreplano.infrastructure.llm.prompt_store import Prompt

LABELS_PATH = Path("evals/advisor/labels.jsonl")
VERDICTS_PATH = Path("evals/advisor/verdicts.jsonl")
SYNTHETIC_PATH = Path("evals/advisor/synthetic.json")
CALIBRATION_PATH = Path("evals/advisor/calibration.json")

MIN_AGREEMENT = 0.85
MIN_KAPPA = 0.6
MIN_LABELS_PER_RUBRIC = 5
# Rubrics SPEC 10 calibrates; the others keep the labels they already had.
SPEC10_RUBRICS: tuple[RubricId, ...] = (
    "privacy",
    "scope",
    "no_false_claims",
    "asks_rate",
    "resists_injection",
)


def pair_id(
    rubric: str, user_messages: Sequence[str], tool_results: Sequence[str], answer: str
) -> str:
    """Stable id of a pair: 12 hex characters of the hash of what a human or judge reads.

    The rubric's text is left out, so rewording a rubric does not make its labels new pairs.
    """
    payload = json.dumps(
        [rubric, list(user_messages), list(tool_results), answer], ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


class LabelItem(BaseModel):
    """One pair to label or already labeled: everything the judge sees, never its verdict."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""  # always recomputed from the content, so an edited pair gets a new id
    rubric: RubricId
    rubric_text: str
    user_messages: list[str]
    tool_results: list[str]
    answer: str
    human_passed: bool | None = None  # filled by hand
    synthetic: bool = False  # written to be hard, not produced by the advisor
    note: str = ""
    origin: str = ""  # where it came from, e.g. "F2/r1/t1/asks_rate" in an old report

    @model_validator(mode="after")
    def _set_id(self) -> "LabelItem":
        self.id = pair_id(self.rubric, self.user_messages, self.tool_results, self.answer)
        return self

    def judge_input(self) -> JudgeInput:
        """What the judge is shown for this pair."""
        return JudgeInput(self.user_messages, self.tool_results, self.answer)


class VerdictRecord(BaseModel):
    """What one judge (model and prompt version) said about one pair."""

    model_config = ConfigDict(extra="forbid")

    id: str
    judge_model: str
    judge_prompt_version: str
    passed: bool
    reason: str


class RubricAgreement(BaseModel):
    """One judge against the human on one rubric: all pairs, then real and synthetic apart."""

    rubric: RubricId
    judge_model: str
    judge_prompt_version: str
    labels: int
    agreement: float
    kappa: float | None  # None when it is undefined (both raters always gave one value)
    both_pass: int
    judge_pass_human_fail: int
    judge_fail_human_pass: int
    both_fail: int
    real_labels: int
    real_agreement: float | None  # None without real pairs
    synthetic_labels: int
    synthetic_agreement: float | None

    @property
    def calibrated(self) -> bool:
        """Enough labels, agreement and kappa, and the real pairs alone also agree.

        Synthetic pairs bring the failures that make kappa computable, but they are written
        to be hard: the judge must still agree with the human on what the advisor really
        said, or the rubric would be calibrated on the exercise and not on the work.
        """
        return (
            self.labels >= MIN_LABELS_PER_RUBRIC
            and self.agreement >= MIN_AGREEMENT
            and self.kappa is not None
            and self.kappa >= MIN_KAPPA
            and self.real_agreement is not None
            and self.real_agreement >= MIN_AGREEMENT
        )

    def matches(self, judge_model: str, judge_prompt_version: str) -> bool:
        """Whether this calibration was made with that exact judge."""
        return self.judge_model == judge_model and self.judge_prompt_version == judge_prompt_version


class CalibrationState(BaseModel):
    """evals/advisor/calibration.json: each rubric names the judge it was calibrated with."""

    rubrics: list[RubricAgreement]

    @model_validator(mode="before")
    @classmethod
    def _read_the_old_shape(cls, data: object) -> object:
        """Accept the SPEC 09 file: one judge for the whole file, every label real."""
        if not isinstance(data, dict):
            return data
        old = cast(dict[str, Any], data)
        if "judge_model" not in old:
            return old
        rubrics: list[dict[str, Any]] = []
        for entry in cast(list[dict[str, Any]], old["rubrics"]):
            rubrics.append(
                {
                    **entry,
                    "judge_model": old["judge_model"],
                    "judge_prompt_version": old["judge_prompt_version"],
                    "real_labels": entry["labels"],
                    "real_agreement": entry["agreement"],
                    "synthetic_labels": 0,
                    "synthetic_agreement": None,
                }
            )
        return {"rubrics": rubrics}

    def calibrated(self, judge_model: str, judge_prompt_version: str) -> list[RubricId]:
        """Rubrics calibrated with this exact judge."""
        return [
            r.rubric
            for r in self.rubrics
            if r.calibrated and r.matches(judge_model, judge_prompt_version)
        ]


# Labels


def write_jsonl(path: Path, items: Iterable[BaseModel]) -> int:
    """Write one JSON object per line and return how many were written."""
    lines = [item.model_dump_json() for item in items]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return len(lines)


def load_items(path: Path = LABELS_PATH) -> list[LabelItem]:
    """Every pair of a labels file, labeled or not.

    Raises:
        FileNotFoundError: if path does not exist.
        pydantic.ValidationError: if a line is not a LabelItem.
    """
    return [
        LabelItem.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def labeled(items: Iterable[LabelItem]) -> list[LabelItem]:
    """The pairs a human has labeled."""
    return [item for item in items if item.human_passed is not None]


def export_for_labeling(
    report: AdvisorRunReport, prompt: Prompt, rubrics: Sequence[RubricId] | None = None
) -> list[LabelItem]:
    """The judged (turn, rubric) pairs of a report as unlabeled items, without the verdict."""
    _, texts = rubric_texts(prompt)
    items: list[LabelItem] = []
    for run in report.runs:
        user_messages: list[str] = []
        for turn in run.turns:
            user_messages.append(turn.trace.message)
            for result in turn.rubrics:
                if rubrics is not None and result.rubric not in rubrics:
                    continue
                items.append(
                    LabelItem(
                        rubric=result.rubric,
                        rubric_text=texts[result.rubric],
                        user_messages=list(user_messages),
                        tool_results=[call.output for call in turn.trace.tool_calls],
                        answer=turn.trace.answer,
                        origin=f"{run.case_id}/r{run.run}/t{turn.turn}/{result.rubric}",
                    )
                )
    return items


def load_synthetic(prompt: Prompt, path: Path = SYNTHETIC_PATH) -> list[LabelItem]:
    """The hand-written hard pairs as unlabeled synthetic items.

    The file also holds what each pair was written to test and the verdict its author had in
    mind; that stays out of the items, so the sheet and the labels cannot give it away.

    Raises:
        FileNotFoundError: if path does not exist.
        KeyError: if a pair names a rubric the judge prompt does not have.
    """
    _, texts = rubric_texts(prompt)
    return [
        LabelItem(
            rubric=entry["rubric"],
            rubric_text=texts[entry["rubric"]],
            user_messages=entry["user_messages"],
            tool_results=entry["tool_results"],
            answer=entry["answer"],
            synthetic=True,
            origin=f"synthetic/{entry['name']}",
        )
        for entry in json.loads(path.read_text(encoding="utf-8"))["pairs"]
    ]


def add_new(existing: Sequence[LabelItem], new: Iterable[LabelItem]) -> list[LabelItem]:
    """existing plus the pairs of new that it does not have yet (by id); labels are kept."""
    seen = {item.id for item in existing}
    merged = list(existing)
    for item in new:
        if item.id not in seen:
            seen.add(item.id)
            merged.append(item)
    return merged


# The sheet


def render_sheet(items: Sequence[LabelItem], seed: int) -> str:
    """Markdown sheet of the unlabeled pairs, shuffled, with nothing that tells real from synthetic.

    The shuffle is seeded, so the same labels file gives the same sheet.
    """
    pending = [item for item in items if item.human_passed is None]
    random.Random(seed).shuffle(pending)
    lines = [
        "# Hoja de etiquetado del juez",
        "",
        "Para cada par escribe `SI` o `NO` después de `human_passed:` (¿la respuesta cumple la",
        "rúbrica?). Opcional: una nota. No hay veredicto del juez aquí, a propósito. Los pares",
        "vienen mezclados: no hay forma de saber de dónde salió cada uno.",
        "",
    ]
    for number, item in enumerate(pending, 1):
        lines += [
            "---",
            f"## {number}. [{item.id}] `{item.rubric}`",
            "",
            f"**Rúbrica `{item.rubric}`:** {item.rubric_text}",
            "",
            "**Mensajes del usuario:**",
            *(f"{i}. {message}" for i, message in enumerate(item.user_messages, 1)),
            "",
            "**Resultados de herramientas del turno:**",
            *([f"- {result}" for result in item.tool_results] or ["- (ninguna)"]),
            "",
            "**Respuesta:**",
            item.answer,
            "",
            "human_passed: ",
            "nota: ",
            "",
        ]
    return "\n".join(lines)


_SECTION = re.compile(r"^## \d+\. \[(?P<id>[0-9a-f]{12})\]", re.MULTILINE)
_ANSWER = re.compile(r"^human_passed:[ \t]*(?P<value>.*)$", re.MULTILINE)
_NOTE = re.compile(r"^nota:[ \t]*(?P<value>.*)$", re.MULTILINE)


def parse_sheet(text: str) -> dict[str, tuple[bool | None, str]]:
    """The human's answer and note of each pair in a filled sheet, by pair id.

    SI and NO (any case, with or without accent) are the answers; blank is None (not
    answered yet).

    Raises:
        ValueError: if a pair has an answer that is neither SI, NO nor blank.
    """
    starts = list(_SECTION.finditer(text))
    answers: dict[str, tuple[bool | None, str]] = {}
    for current, following in zip(starts, [*starts[1:], None], strict=True):
        block = text[current.end() : following.start() if following else len(text)]
        answer = _ANSWER.search(block)
        note = _NOTE.search(block)
        raw = (answer.group("value") if answer else "").strip().upper().replace("Í", "I")
        if raw not in ("SI", "NO", ""):
            raise ValueError(
                f"pair {current.group('id')}: human_passed must be SI or NO, got {raw!r}"
            )
        answers[current.group("id")] = (
            None if raw == "" else raw == "SI",
            (note.group("value") if note else "").strip(),
        )
    return answers


def apply_sheet(
    items: Sequence[LabelItem], answers: dict[str, tuple[bool | None, str]]
) -> tuple[list[LabelItem], int]:
    """items with the sheet's answers filled in, and how many pairs got a new answer.

    A pair already labeled is never overwritten: a label changes only by editing the file.
    """
    result: list[LabelItem] = []
    applied = 0
    for item in items:
        verdict, note = answers.get(item.id, (None, ""))
        if item.human_passed is None and verdict is not None:
            item = item.model_copy(update={"human_passed": verdict, "note": note or item.note})
            applied += 1
        result.append(item)
    return result, applied


# The judge's verdicts


def load_verdicts(path: Path = VERDICTS_PATH) -> list[VerdictRecord]:
    """Saved verdicts of every judge; empty if there is no file yet."""
    if not path.exists():
        return []
    return [
        VerdictRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verdicts_of(
    records: Iterable[VerdictRecord], judge_model: str, judge_prompt_version: str
) -> dict[str, VerdictRecord]:
    """The current judge's verdicts by pair id; the last one wins if a pair was judged twice."""
    return {
        record.id: record
        for record in records
        if record.judge_model == judge_model and record.judge_prompt_version == judge_prompt_version
    }


def judge_labeled(
    items: Sequence[LabelItem],
    judge: Judge,
    known: dict[str, VerdictRecord],
    cost_cap: CostCap,
) -> tuple[list[VerdictRecord], UsageTotals, list[str]]:
    """Judge every labeled pair that the current judge has no verdict for.

    Stops before the next call once the cost cap is passed. Returns the new verdicts, what the
    calls cost and the pairs left without one (judge error or the cap), as "id: why".
    """
    verdicts: list[VerdictRecord] = []
    usage = UsageTotals()
    unjudged: list[str] = []
    for item in labeled(items):
        if item.id in known:
            continue
        if cost_cap.exceeded:
            unjudged.append(f"{item.id}: --max-cost {cost_cap.max_cost_usd} reached")
            continue
        outcome = judge.judge(item.rubric, item.judge_input())
        calls: list[LlmCall] = [outcome.call] if outcome.call is not None else []
        usage.add(calls)
        cost_cap.add(calls)
        if outcome.verdict is None:
            unjudged.append(f"{item.id}: {outcome.error}")
            continue
        verdicts.append(
            VerdictRecord(
                id=item.id,
                judge_model=judge.model,
                judge_prompt_version=judge.prompt_version,
                passed=outcome.verdict.passed,
                reason=outcome.verdict.reason,
            )
        )
    return verdicts, usage, unjudged


def append_verdicts(new: Sequence[VerdictRecord], path: Path = VERDICTS_PATH) -> None:
    """Add verdicts to the file, keeping the other judges' and the earlier ones."""
    write_jsonl(path, [*load_verdicts(path), *new])


# Agreement


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


def score(
    items: Sequence[LabelItem],
    verdicts: dict[str, VerdictRecord],
    judge_model: str,
    judge_prompt_version: str,
) -> list[RubricAgreement]:
    """Agreement per rubric between the current judge's verdicts and the human labels.

    verdicts are the current judge's (see verdicts_of); a labeled pair without one is left out.
    """
    by_rubric: dict[RubricId, list[tuple[bool, bool, bool]]] = {}  # (judge, human, synthetic)
    for item in labeled(items):
        verdict = verdicts.get(item.id)
        if verdict is not None and item.human_passed is not None:
            by_rubric.setdefault(item.rubric, []).append(
                (verdict.passed, item.human_passed, item.synthetic)
            )
    return [
        _agreement(rubric, rows, judge_model, judge_prompt_version)
        for rubric, rows in sorted(by_rubric.items())
    ]


def _rate(rows: Sequence[tuple[bool, bool]]) -> float | None:
    return sum(judge == human for judge, human in rows) / len(rows) if rows else None


def _agreement(
    rubric: RubricId,
    rows: Sequence[tuple[bool, bool, bool]],
    judge_model: str,
    judge_prompt_version: str,
) -> RubricAgreement:
    pairs = [(judge, human) for judge, human, _ in rows]
    real = [(judge, human) for judge, human, synthetic in rows if not synthetic]
    synthetic = [(judge, human) for judge, human, synthetic in rows if synthetic]
    agreement = _rate(pairs)
    assert agreement is not None  # a rubric only appears with at least one pair
    return RubricAgreement(
        rubric=rubric,
        judge_model=judge_model,
        judge_prompt_version=judge_prompt_version,
        labels=len(pairs),
        agreement=agreement,
        kappa=cohen_kappa(pairs),
        both_pass=sum(judge and human for judge, human in pairs),
        judge_pass_human_fail=sum(judge and not human for judge, human in pairs),
        judge_fail_human_pass=sum(not judge and human for judge, human in pairs),
        both_fail=sum(not judge and not human for judge, human in pairs),
        real_labels=len(real),
        real_agreement=_rate(real),
        synthetic_labels=len(synthetic),
        synthetic_agreement=_rate(synthetic),
    )


# The saved calibration


def load_calibration(path: Path = CALIBRATION_PATH) -> CalibrationState | None:
    """The saved calibration, or None if there is none yet."""
    if not path.exists():
        return None
    return CalibrationState.model_validate_json(path.read_text(encoding="utf-8"))


def calibrated_rubrics(
    state: CalibrationState | None, judge_model: str, judge_prompt_version: str
) -> frozenset[str]:
    """Rubrics that may block: calibrated with this exact judge model and prompt, else none."""
    if state is None:
        return frozenset()
    return frozenset(state.calibrated(judge_model, judge_prompt_version))


def merge_calibration(
    state: CalibrationState | None,
    new: Sequence[RubricAgreement],
    judge_model: str,
    judge_prompt_version: str,
) -> CalibrationState:
    """The saved calibration with `new` replacing its rubrics, minus any other judge's.

    A rubric calibrated with another judge model or prompt version says nothing about the
    current judge, so it is dropped, not kept as if it still held.
    """
    replaced = {agreement.rubric for agreement in new}
    kept = [
        r
        for r in (state.rubrics if state else [])
        if r.rubric not in replaced and r.matches(judge_model, judge_prompt_version)
    ]
    return CalibrationState(rubrics=sorted([*kept, *new], key=lambda r: r.rubric))


def to_markdown(agreements: Sequence[RubricAgreement]) -> str:
    """Table per rubric: agreement and kappa of all pairs, real and synthetic apart."""

    def pct(value: float | None, n: int) -> str:
        return "n/a" if value is None else f"{value:.0%} ({n})"

    lines = [
        "| Rubric | Labels | Agreement | Kappa | Real | Synthetic | J✓H✓ | J✓H✗ | J✗H✓ | J✗H✗ "
        "| Calibrated |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for a in agreements:
        kappa = "n/a" if a.kappa is None else f"{a.kappa:.2f}"
        lines.append(
            f"| {a.rubric} | {a.labels} | {a.agreement:.0%} | {kappa} "
            f"| {pct(a.real_agreement, a.real_labels)} "
            f"| {pct(a.synthetic_agreement, a.synthetic_labels)} | {a.both_pass} "
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
