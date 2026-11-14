"""Unit tests for judge calibration: kappa, agreement, export and the calibration state."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sobreplano.domain.advisor import ToolCallRecord
from sobreplano.evals.advisor.calibration import (
    CalibrationState,
    LabelItem,
    RubricAgreement,
    calibrated_rubrics,
    cohen_kappa,
    export_for_labeling,
    label_key,
    load_labels,
    score,
    write_jsonl,
)
from sobreplano.evals.advisor.cases import RubricId
from sobreplano.evals.advisor.checks import TurnTrace
from sobreplano.evals.advisor.judge import judge_prompt
from sobreplano.evals.advisor.runner import AdvisorRunReport, CaseRun, RubricResult, TurnResult
from sobreplano.evals.report import UsageTotals

NOW = datetime(2026, 11, 13, tzinfo=UTC)


def test_kappa_perfect_agreement_is_one() -> None:
    assert cohen_kappa([(True, True), (False, False), (True, True)]) == 1.0


def test_kappa_known_value() -> None:
    # 10 pairs: 4 both pass, 1 judge-only pass, 1 human-only pass, 4 both fail.
    pairs = [(True, True)] * 4 + [(True, False)] + [(False, True)] + [(False, False)] * 4
    # observed 0.8, expected 0.5*0.5 + 0.5*0.5 = 0.5, kappa 0.6.
    assert cohen_kappa(pairs) == pytest.approx(0.6)


def test_kappa_agreement_no_better_than_chance_is_zero() -> None:
    pairs = [(True, True), (True, False), (False, True), (False, False)]
    assert cohen_kappa(pairs) == pytest.approx(0.0)


def test_kappa_is_undefined_when_both_always_say_the_same() -> None:
    assert cohen_kappa([(True, True)] * 5) is None
    assert cohen_kappa([]) is None


def agreement(labels: int, agreement: float, kappa: float | None) -> RubricAgreement:
    return RubricAgreement(
        rubric="helpful",
        labels=labels,
        agreement=agreement,
        kappa=kappa,
        both_pass=0,
        judge_pass_human_fail=0,
        judge_fail_human_pass=0,
        both_fail=0,
    )


@pytest.mark.parametrize(
    ("labels", "value", "kappa", "calibrated"),
    [
        (5, 0.85, 0.6, True),
        (4, 1.0, 1.0, False),
        (10, 0.84, 0.9, False),
        (10, 0.9, 0.59, False),
        (10, 1.0, None, False),
    ],
)
def test_calibrated_needs_labels_agreement_and_kappa(
    labels: int, value: float, kappa: float | None, calibrated: bool
) -> None:
    assert agreement(labels, value, kappa).calibrated is calibrated


def rubric(name: RubricId, passed: bool | None) -> RubricResult:
    return RubricResult(rubric=name, passed=passed, reason="r", blocking=False)


def make_report(*verdicts: tuple[RubricId, bool | None]) -> AdvisorRunReport:
    turn = TurnResult(
        turn=1,
        trace=TurnTrace(
            message="¿Y la cuota?",
            answer="Cuota de $2.964.145; es aproximada.",
            tool_calls=[ToolCallRecord("simulate_mortgage", {"years": 20}, '{"months":240}')],
            llm_calls=[],
        ),
        checks=[],
        seconds=1.0,
        rubrics=[rubric(name, passed) for name, passed in verdicts],
    )
    return AdvisorRunReport(
        model="openai:gpt-6-luna",
        judge_model="openai:gpt-6.1-terra",
        calibrated_rubrics=[],
        prompt_versions={"judge": judge_prompt().version},
        commit=None,
        started_at=NOW,
        finished_at=NOW,
        repeat=1,
        max_cost_usd=Decimal(1),
        case_ids=["F1"],
        complete=True,
        stop_reason=None,
        runs=[CaseRun(case_id="F1", category="finance", run=1, thread_id="t", turns=[turn])],
        advisor_usage=UsageTotals(),
        judge_usage=UsageTotals(),
    )


def test_export_has_what_the_judge_saw_but_not_its_verdict(tmp_path: Path) -> None:
    report = make_report(("simulation_caveat", True), ("helpful", False))
    items = export_for_labeling(report, judge_prompt())

    assert [item.key for item in items] == ["F1/r1/t1/simulation_caveat", "F1/r1/t1/helpful"]
    first = items[0]
    assert first.user_messages == ["¿Y la cuota?"]
    assert first.tool_results == ['{"months":240}']
    assert "insurance" in first.rubric_text
    assert first.human_passed is None
    path = tmp_path / "to_label.jsonl"
    assert write_jsonl(path, items) == 2
    assert '"passed"' not in path.read_text() and '"reason"' not in path.read_text()


def test_load_labels_skips_unlabeled_items(tmp_path: Path) -> None:
    base = LabelItem(
        key="a", rubric="scope", rubric_text="", user_messages=[], tool_results=[], answer=""
    )
    path = tmp_path / "labels.jsonl"
    write_jsonl(
        path,
        [base, base.model_copy(update={"key": "b", "human_passed": False})],
    )
    assert load_labels(path) == {"b": False}


def test_score_builds_the_confusion_matrix_and_skips_judge_errors() -> None:
    report = make_report(("simulation_caveat", True), ("helpful", False), ("scope", None))
    labels = {
        label_key("F1", 1, 1, "simulation_caveat"): True,
        label_key("F1", 1, 1, "helpful"): True,
        label_key("F1", 1, 1, "scope"): True,
    }
    by_rubric = {a.rubric: a for a in score(report, labels)}

    assert set(by_rubric) == {"helpful", "simulation_caveat"}
    assert (by_rubric["simulation_caveat"].both_pass, by_rubric["simulation_caveat"].agreement) == (
        1,
        1.0,
    )
    assert by_rubric["helpful"].judge_fail_human_pass == 1


def test_calibration_only_counts_for_the_same_judge_prompt() -> None:
    state = CalibrationState(
        judge_model="openai:gpt-6.1-terra",
        judge_prompt_version="aaaaaaaaaaaa",
        report="r.json",
        rubrics=[agreement(10, 0.9, 0.8)],
    )
    assert calibrated_rubrics(state, "aaaaaaaaaaaa") == {"helpful"}
    assert calibrated_rubrics(state, "bbbbbbbbbbbb") == frozenset()
    assert calibrated_rubrics(None, "aaaaaaaaaaaa") == frozenset()
