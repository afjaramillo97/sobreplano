"""Unit tests for judge calibration: pairs, sheet, verdicts, agreement and saved calibration."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from sobreplano.domain.advisor import LlmCall, ToolCallRecord
from sobreplano.evals.advisor.__main__ import main
from sobreplano.evals.advisor.calibration import (
    LABELS_PATH,
    SPEC10_RUBRICS,
    SYNTHETIC_PATH,
    CalibrationState,
    LabelItem,
    RubricAgreement,
    VerdictRecord,
    add_new,
    apply_sheet,
    calibrated_rubrics,
    cohen_kappa,
    export_for_labeling,
    judge_labeled,
    labeled,
    load_calibration,
    load_items,
    load_synthetic,
    merge_calibration,
    pair_id,
    parse_sheet,
    render_sheet,
    score,
    to_markdown,
    verdicts_of,
    write_jsonl,
)
from sobreplano.evals.advisor.cases import RubricId
from sobreplano.evals.advisor.checks import TurnTrace
from sobreplano.evals.advisor.judge import (
    JudgeInput,
    JudgeOutcome,
    Verdict,
    judge_prompt,
)
from sobreplano.evals.advisor.runner import AdvisorRunReport, CaseRun, RubricResult, TurnResult
from sobreplano.evals.report import CostCap, UsageTotals

NOW = datetime(2026, 11, 13, tzinfo=UTC)
JUDGE = "openai:gpt-6.1-terra"
VERSION = "75d053a91f88"


def item(
    rubric: RubricId = "scope",
    answer: str = "Respuesta",
    *,
    passed: bool | None = None,
    synthetic: bool = False,
    messages: list[str] | None = None,
) -> LabelItem:
    return LabelItem(
        rubric=rubric,
        rubric_text="Texto de la rúbrica",
        user_messages=messages or ["Hola"],
        tool_results=[],
        answer=answer,
        human_passed=passed,
        synthetic=synthetic,
    )


def verdict(
    of: LabelItem, passed: bool, judge: str = JUDGE, version: str = VERSION
) -> VerdictRecord:
    return VerdictRecord(
        id=of.id, judge_model=judge, judge_prompt_version=version, passed=passed, reason="r"
    )


# kappa


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


# the pair is the label


def test_the_pair_id_depends_on_what_is_read_and_not_on_the_rubric_text() -> None:
    base = pair_id("scope", ["Hola"], [], "Respuesta")
    assert base == pair_id("scope", ["Hola"], [], "Respuesta")
    assert base != pair_id("privacy", ["Hola"], [], "Respuesta")
    assert base != pair_id("scope", ["Hola"], [], "Otra")
    assert item().id == base  # the rubric text does not enter


def test_the_id_is_recomputed_so_an_edited_pair_gets_a_new_one() -> None:
    first = item(answer="Una")
    edited = LabelItem.model_validate({**first.model_dump(), "answer": "Otra"})
    assert edited.id != first.id and edited.id == item(answer="Otra").id


def test_a_label_has_no_report_key_and_keeps_where_it_came_from() -> None:
    dumped = item().model_dump()
    assert "key" not in dumped
    assert {"human_passed", "synthetic", "origin"} <= set(dumped)


# export and synthetic


def rubric_result(name: RubricId) -> RubricResult:
    return RubricResult(rubric=name, passed=True, reason="r", blocking=False)


def make_report(*rubrics: RubricId) -> AdvisorRunReport:
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
        rubrics=[rubric_result(name) for name in rubrics],
    )
    return AdvisorRunReport(
        model="openai:gpt-6-luna",
        judge_model=JUDGE,
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
    items = export_for_labeling(make_report("simulation_caveat", "helpful"), judge_prompt())

    assert [i.origin for i in items] == ["F1/r1/t1/simulation_caveat", "F1/r1/t1/helpful"]
    first = items[0]
    assert first.user_messages == ["¿Y la cuota?"]
    assert first.tool_results == ['{"months":240}']
    assert "insurance" in first.rubric_text
    assert first.human_passed is None and not first.synthetic
    path = tmp_path / "labels.jsonl"
    write_jsonl(path, items)
    assert '"passed"' not in path.read_text() and '"reason"' not in path.read_text()


def test_export_can_keep_only_some_rubrics() -> None:
    report = make_report("simulation_caveat", "helpful", "scope")
    kept = export_for_labeling(report, judge_prompt(), ["scope", "helpful"])
    assert [i.rubric for i in kept] == ["helpful", "scope"]


def test_the_synthetic_file_has_hard_pairs_for_the_four_rubrics() -> None:
    raw = json.loads(SYNTHETIC_PATH.read_text(encoding="utf-8"))["pairs"]
    for rubric in SPEC10_RUBRICS:
        pairs = [p for p in raw if p["rubric"] == rubric]
        assert sum(not p["intended_pass"] for p in pairs) >= 2, rubric  # failures to measure kappa
        assert sum(p["intended_pass"] for p in pairs) >= 2, rubric  # passes that look like failures
        assert all(p["trick"] for p in pairs)
    assert len({(p["rubric"], p["answer"]) for p in raw}) == len(raw)


def test_loaded_synthetic_pairs_are_unlabeled_and_do_not_reveal_the_intended_verdict() -> None:
    items = load_synthetic(judge_prompt())
    assert items and all(i.synthetic and i.human_passed is None for i in items)
    dumped = json.dumps([i.model_dump() for i in items])
    assert "intended" not in dumped and "trick" not in dumped
    assert len({i.id for i in items}) == len(items)


def test_add_new_keeps_existing_labels_and_skips_pairs_it_has() -> None:
    labeled_item = item(answer="A", passed=True)
    merged = add_new([labeled_item], [item(answer="A"), item(answer="B")])
    assert [(i.answer, i.human_passed) for i in merged] == [("A", True), ("B", None)]


# the sheet


def test_the_sheet_has_only_unlabeled_pairs_shuffled_and_nothing_that_gives_the_source() -> None:
    items = [item(answer=f"Respuesta {n}", synthetic=n % 2 == 0) for n in range(8)]
    items.append(item(answer="ya etiquetada", passed=True))
    sheet = render_sheet(items, seed=10)

    assert "ya etiquetada" not in sheet
    ids = re.findall(r"^## \d+\. \[([0-9a-f]{12})\]", sheet, re.MULTILINE)
    assert len(ids) == 8
    assert ids != [i.id for i in items[:8]]  # shuffled
    assert sheet == render_sheet(items, seed=10)  # same seed, same sheet
    assert sheet != render_sheet(items, seed=11)
    for forbidden in ("synthetic", "sintético", "origin", "real"):
        assert forbidden not in sheet.lower().replace("**rúbrica", "")


def test_the_sheet_never_shows_a_judge_verdict() -> None:
    sheet = render_sheet([item()], seed=1)
    assert "passed" not in sheet.replace("human_passed", "") and "reason" not in sheet


def filled(sheet: str, answers: dict[int, str]) -> str:
    """Write each answer after the human_passed of the numbered pair."""
    sections = sheet.split("\n---\n")
    for number, answer in answers.items():
        sections[number] = sections[number].replace("human_passed: ", f"human_passed: {answer}", 1)
    return "\n---\n".join(sections)


def test_a_filled_sheet_is_read_back_by_pair_id() -> None:
    items = [item(answer=f"R{n}") for n in range(4)]
    sheet = render_sheet(items, seed=3)
    text = filled(sheet, {1: "SI", 2: "no", 3: "Sí"}).replace("nota: ", "nota: ojo", 1)
    answers = parse_sheet(text)

    by_position = [m.group(1) for m in re.finditer(r"^## \d+\. \[([0-9a-f]{12})\]", sheet, re.M)]
    assert answers[by_position[0]] == (True, "ojo")
    assert answers[by_position[1]][0] is False  # "no" in lowercase
    assert answers[by_position[2]][0] is True  # "Sí" with its accent
    assert answers[by_position[3]] == (None, "")  # left blank: not answered yet


def test_an_answer_that_is_not_si_or_no_is_an_error() -> None:
    sheet = render_sheet([item()], seed=1)
    with pytest.raises(ValueError, match="SI or NO"):
        parse_sheet(filled(sheet, {1: "tal vez"}))


def test_apply_sheet_fills_blank_labels_and_never_overwrites_one() -> None:
    open_item, done = item(answer="A"), item(answer="B", passed=True)
    updated, applied = apply_sheet(
        [open_item, done], {open_item.id: (False, "nota"), done.id: (False, "")}
    )
    assert applied == 1
    assert (updated[0].human_passed, updated[0].note) == (False, "nota")
    assert updated[1].human_passed is True


# the judge's verdicts


class FakeJudge:
    model = JUDGE
    prompt_version = VERSION

    def __init__(
        self, passing: set[str] | None = None, failing_call: set[str] | None = None
    ) -> None:
        self.calls: list[JudgeInput] = []
        self.passing = passing or set()
        self.error_for = failing_call or set()

    def judge(self, rubric: RubricId, data: JudgeInput) -> JudgeOutcome:
        self.calls.append(data)
        call = LlmCall(JUDGE, 1000, 100, Decimal("0.01"), VERSION)
        if data.answer in self.error_for:
            return JudgeOutcome(None, call, "answer cut off or filtered")
        return JudgeOutcome(Verdict(reason="r", passed=data.answer in self.passing), call)


def test_judge_labeled_judges_only_labeled_pairs_without_a_verdict_of_this_judge() -> None:
    a, b, c, unlabeled = (item(answer=x, passed=True) for x in "abc"), None, None, item(answer="u")
    a, b, c = a
    known = {a.id: verdict(a, True)}
    judge = FakeJudge(passing={"b"})

    verdicts, usage, unjudged = judge_labeled(
        [a, b, c, unlabeled], judge, known, CostCap(Decimal(1))
    )

    assert [v.id for v in verdicts] == [b.id, c.id]
    assert [v.passed for v in verdicts] == [True, False]
    assert (verdicts[0].judge_model, verdicts[0].judge_prompt_version) == (JUDGE, VERSION)
    assert len(judge.calls) == 2 and usage.cost_usd == Decimal("0.02") and unjudged == []


def test_a_judge_error_leaves_the_pair_without_a_verdict() -> None:
    a = item(answer="a", passed=True)
    verdicts, _, unjudged = judge_labeled(
        [a], FakeJudge(failing_call={"a"}), {}, CostCap(Decimal(1))
    )
    assert verdicts == []
    assert unjudged == [f"{a.id}: answer cut off or filtered"]


def test_the_cost_cap_stops_the_judge_before_the_next_call() -> None:
    items = [item(answer=str(n), passed=True) for n in range(5)]
    judge = FakeJudge()
    verdicts, _, unjudged = judge_labeled(items, judge, {}, CostCap(Decimal("0.015")))
    assert len(verdicts) == len(judge.calls) == 2  # 0.01 + 0.01 passes 0.015
    assert len(unjudged) == 3 and "--max-cost" in unjudged[0]


def test_verdicts_of_keeps_only_the_current_judge_and_the_last_verdict() -> None:
    a = item(answer="a")
    records = [
        verdict(a, True, judge="other:model"),
        verdict(a, True, version="old"),
        verdict(a, True),
        verdict(a, False),
    ]
    assert verdicts_of(records, JUDGE, VERSION)[a.id].passed is False
    assert verdicts_of(records[:2], JUDGE, VERSION) == {}


# agreement


def test_score_splits_real_and_synthetic_and_skips_pairs_without_a_verdict() -> None:
    real_ok = item(answer="r1", passed=True)
    real_bad = item(answer="r2", passed=False)
    synth_ok = item(answer="s1", passed=False, synthetic=True)
    synth_bad = item(answer="s2", passed=True, synthetic=True)
    no_verdict = item(answer="x", passed=True)
    verdicts = {
        real_ok.id: verdict(real_ok, True),
        real_bad.id: verdict(real_bad, False),
        synth_ok.id: verdict(synth_ok, False),
        synth_bad.id: verdict(synth_bad, False),  # the judge disagrees on this one
    }
    [result] = score([real_ok, real_bad, synth_ok, synth_bad, no_verdict], verdicts, JUDGE, VERSION)

    assert (result.labels, result.agreement) == (4, 0.75)
    assert (result.real_labels, result.real_agreement) == (2, 1.0)
    assert (result.synthetic_labels, result.synthetic_agreement) == (2, 0.5)
    assert (result.both_pass, result.both_fail, result.judge_fail_human_pass) == (1, 2, 1)
    assert (result.judge_model, result.judge_prompt_version) == (JUDGE, VERSION)


def agreement(
    labels: int = 10,
    value: float = 0.9,
    kappa: float | None = 0.8,
    *,
    real: float | None = 1.0,
    rubric: RubricId = "helpful",
    judge: str = JUDGE,
    version: str = VERSION,
) -> RubricAgreement:
    return RubricAgreement(
        rubric=rubric,
        judge_model=judge,
        judge_prompt_version=version,
        labels=labels,
        agreement=value,
        kappa=kappa,
        both_pass=0,
        judge_pass_human_fail=0,
        judge_fail_human_pass=0,
        both_fail=0,
        real_labels=0 if real is None else labels,
        real_agreement=real,
        synthetic_labels=0,
        synthetic_agreement=None,
    )


@pytest.mark.parametrize(
    ("labels", "value", "kappa", "real", "calibrated"),
    [
        (5, 0.85, 0.6, 0.85, True),
        (4, 1.0, 1.0, 1.0, False),
        (10, 0.84, 0.9, 1.0, False),
        (10, 0.9, 0.59, 1.0, False),
        (10, 1.0, None, 1.0, False),
        # Synthetic pairs make the overall numbers good, the real ones alone are not:
        (10, 0.9, 0.8, 0.84, False),
        (10, 0.9, 0.8, None, False),
    ],
)
def test_calibrated_needs_every_threshold_and_the_real_pairs_alone_to_agree(
    labels: int, value: float, kappa: float | None, real: float | None, calibrated: bool
) -> None:
    assert agreement(labels, value, kappa, real=real).calibrated is calibrated


def test_the_markdown_shows_real_and_synthetic_apart() -> None:
    table = to_markdown([agreement(real=1.0)])
    assert "| Real | Synthetic |" in table
    assert "100% (10)" in table and "n/a" in table


# the saved calibration


def test_a_rubric_blocks_only_with_the_judge_model_and_prompt_it_was_calibrated_with() -> None:
    state = CalibrationState(rubrics=[agreement()])
    assert calibrated_rubrics(state, JUDGE, VERSION) == {"helpful"}
    assert calibrated_rubrics(state, JUDGE, "bbbbbbbbbbbb") == frozenset()
    assert calibrated_rubrics(state, "openai:gpt-6.1-sol", VERSION) == frozenset()
    assert calibrated_rubrics(None, JUDGE, VERSION) == frozenset()


def test_merging_replaces_the_scored_rubrics_keeps_the_others_and_drops_other_judges() -> None:
    old = CalibrationState(
        rubrics=[
            agreement(rubric="price_citation"),  # same judge, not re-scored: kept
            agreement(rubric="helpful", value=0.5),  # re-scored now: replaced
            agreement(rubric="simulation_caveat", version="old-prompt"),  # other judge: dropped
        ]
    )
    new = [agreement(rubric="helpful", value=0.95), agreement(rubric="privacy")]
    merged = merge_calibration(old, new, JUDGE, VERSION)

    assert [r.rubric for r in merged.rubrics] == ["helpful", "price_citation", "privacy"]
    assert next(r for r in merged.rubrics if r.rubric == "helpful").agreement == 0.95
    assert merge_calibration(None, new, JUDGE, VERSION).rubrics == sorted(
        new, key=lambda r: r.rubric
    )


def test_the_spec_09_calibration_file_is_still_read() -> None:
    old = {
        "judge_model": JUDGE,
        "judge_prompt_version": VERSION,
        "report": "advisor-2026-11-14-openai_gpt-6-luna.json",
        "rubrics": [
            {
                "rubric": "price_citation",
                "labels": 46,
                "agreement": 1.0,
                "kappa": 1.0,
                "both_pass": 40,
                "judge_pass_human_fail": 0,
                "judge_fail_human_pass": 0,
                "both_fail": 6,
            }
        ],
    }
    state = CalibrationState.model_validate(old)
    [rubric] = state.rubrics
    assert (rubric.judge_model, rubric.real_labels, rubric.synthetic_labels) == (JUDGE, 46, 0)
    assert calibrated_rubrics(state, JUDGE, VERSION) == {"price_citation"}


def test_the_calibration_in_the_repo_loads() -> None:
    assert load_calibration() is not None


# the migrated labels


def test_the_73_labels_of_spec_09_were_migrated_with_their_text() -> None:
    items = load_items(LABELS_PATH)
    old = [
        i for i in items if not i.synthetic and i.origin and not i.origin.startswith("synthetic")
    ]
    assert len(old) >= 73
    assert all(i.human_passed is not None for i in old[:73])
    assert {i.rubric for i in old} >= {"price_citation", "helpful", "asks_rate", "scope"}
    assert all(i.answer and i.rubric_text and i.user_messages for i in items)
    assert len({i.id for i in items}) == len(items)
    assert len(labeled(items)) >= 73


# the commands


def test_add_sheet_import_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    labels = tmp_path / "labels.jsonl"
    sheet = tmp_path / "hoja.md"
    assert main(["calibrate-add", "--labels", str(labels)]) == 0
    added = load_items(labels)
    assert len(added) == len(load_synthetic(judge_prompt()))

    assert main(["calibrate-sheet", "--labels", str(labels), "--out", str(sheet)]) == 0
    text = sheet.read_text(encoding="utf-8")
    sections = text.split("\n---\n")
    answered = filled(text, {1: "SI", 2: "NO"})
    assert len(sections) == len(added) + 1
    sheet.write_text(answered, encoding="utf-8")

    assert main(["calibrate-import", "--labels", str(labels), "--sheet", str(sheet)]) == 0
    assert len(labeled(load_items(labels))) == 2
    assert "2 labels read" in capsys.readouterr().out
    # Adding again changes nothing.
    assert main(["calibrate-add", "--labels", str(labels)]) == 0
    assert len(load_items(labels)) == len(added)


def test_import_refuses_a_sheet_with_pairs_that_are_not_in_the_labels(tmp_path: Path) -> None:
    labels = tmp_path / "labels.jsonl"
    write_jsonl(labels, [item(answer="x")])
    sheet = tmp_path / "hoja.md"
    sheet.write_text(render_sheet([item(answer="y")], 1), encoding="utf-8")
    assert main(["calibrate-import", "--labels", str(labels), "--sheet", str(sheet)]) == 2
