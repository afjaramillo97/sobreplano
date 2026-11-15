"""Command line of the advisor evals: prepare, run, and calibrate the judge."""

import argparse
from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sqlalchemy.orm import Session

from sobreplano.domain.errors import AdvisorUnavailableError
from sobreplano.evals.advisor.calibration import (
    CALIBRATION_PATH,
    LABELS_PATH,
    SPEC10_RUBRICS,
    SYNTHETIC_PATH,
    VERDICTS_PATH,
    LabelItem,
    add_new,
    append_verdicts,
    apply_sheet,
    calibrated_rubrics,
    export_for_labeling,
    judge_labeled,
    labeled,
    load_calibration,
    load_items,
    load_synthetic,
    load_verdicts,
    merge_calibration,
    parse_sheet,
    render_sheet,
    save_calibration,
    score,
    to_markdown,
    verdicts_of,
    write_jsonl,
)
from sobreplano.evals.advisor.cases import CASES_PATH, EvalCase, load_cases
from sobreplano.evals.advisor.database import (
    CATALOG_PATH,
    UnsafeEvalDatabaseError,
    check_local,
    eval_database_url,
    prepare,
)
from sobreplano.evals.advisor.judge import (
    JudgeUnavailableError,
    OpenAIJudge,
    build_judge,
    judge_model_name,
    judge_prompt,
)
from sobreplano.evals.advisor.runner import AdvisorRunReport, run_advisor_evals
from sobreplano.evals.report import (
    CostCap,
    UnknownPriceError,
    git_commit,
    report_stem,
    require_prices,
    write_report,
)
from sobreplano.infrastructure.advisor.chat_models import build_chat_model
from sobreplano.infrastructure.advisor.graph import SYSTEM_PROMPT
from sobreplano.infrastructure.advisor.grounding import tool_definition_numbers
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.advisor.tracing import (
    langfuse_callbacks,
    score_trace,
    shutdown_tracing,
    traced_span,
    tracing_enabled,
)
from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery
from sobreplano.infrastructure.settings import Settings, load_settings

DEFAULT_MAX_COST_USD = Decimal("0.25")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code (1 if a run fails a threshold)."""
    parser = argparse.ArgumentParser(prog="python -m sobreplano.evals.advisor")
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_parser = commands.add_parser(
        "prepare", help="recreate the evals database (EVAL_DATABASE_URL) and load the catalog"
    )
    prepare_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)

    run_parser = commands.add_parser("run", help="run the cases and write the report")
    run_parser.add_argument("--model", help='"provider:model"; default ADVISOR_MODEL')
    run_parser.add_argument("--repeat", type=int, default=1)
    run_parser.add_argument("--cases", help="comma-separated case ids, e.g. S1,F3")
    run_parser.add_argument("--max-cost", type=Decimal, default=DEFAULT_MAX_COST_USD)
    run_parser.add_argument("--allow-unknown-cost", action="store_true")
    run_parser.add_argument("--cases-file", type=Path, default=CASES_PATH)
    run_parser.add_argument("--no-judge", action="store_true", help="deterministic checks only")

    # Judge calibration (SPEC 10): labeled pairs live in one file, apart from any report.
    add_parser = commands.add_parser(
        "calibrate-add",
        help="add unlabeled pairs to the labels file: a report's real ones and the synthetic ones",
    )
    add_parser.add_argument(
        "--report", type=Path, help="advisor report; omit to add only synthetic"
    )
    add_parser.add_argument(
        "--rubrics",
        default=",".join(SPEC10_RUBRICS),
        help="rubrics to take from the report (default: the four of SPEC 10)",
    )
    add_parser.add_argument("--synthetic", type=Path, default=SYNTHETIC_PATH)
    add_parser.add_argument("--no-synthetic", action="store_true")
    add_parser.add_argument("--labels", type=Path, default=LABELS_PATH)

    sheet_parser = commands.add_parser(
        "calibrate-sheet", help="write the Markdown sheet of the unlabeled pairs, shuffled"
    )
    sheet_parser.add_argument("--out", type=Path, required=True)
    sheet_parser.add_argument("--seed", type=int, default=10)
    sheet_parser.add_argument("--labels", type=Path, default=LABELS_PATH)

    import_parser = commands.add_parser(
        "calibrate-import", help="read a filled sheet into the labels file"
    )
    import_parser.add_argument("--sheet", type=Path, required=True)
    import_parser.add_argument("--labels", type=Path, default=LABELS_PATH)

    judge_parser = commands.add_parser(
        "calibrate-judge",
        help="judge every labeled pair that the current judge has no verdict for (paid)",
    )
    judge_parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    judge_parser.add_argument("--max-cost", type=Decimal, default=Decimal("0.50"))
    judge_parser.add_argument("--allow-unknown-cost", action="store_true")

    score_parser = commands.add_parser(
        "calibrate-score",
        help="agreement of the current judge's verdicts with the labels; saves calibration",
    )
    score_parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    args = parser.parse_args(argv)

    if args.command == "prepare":
        try:
            report = prepare(eval_database_url(), args.catalog)
        except UnsafeEvalDatabaseError as error:
            print(f"refusing to prepare: {error}")
            return 1
        print(report)
        return 0
    if args.command.startswith("calibrate-"):
        try:
            return _calibrate(args)
        except (OSError, ValidationError, ValueError, KeyError) as error:
            print(f"cannot calibrate: {error}")
            return 2
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("--repeat must be at least 1")
        return 2
    settings = load_settings()
    if args.model:
        settings = settings.model_copy(update={"advisor_model": args.model})
    model: str = settings.advisor_model
    judge: OpenAIJudge | None = None
    try:
        cases = _select(load_cases(args.cases_file), args.cases)
        chat_model = build_chat_model(settings)
        if not args.no_judge:
            judge = build_judge(settings, judge_model_name(), advisor_model=model)
        require_prices(
            [model] if judge is None else [model, judge.model],
            allow_unknown=args.allow_unknown_cost,
        )
        url = check_local(eval_database_url()).render_as_string(hide_password=False)
    except (
        ValueError,
        UnknownPriceError,
        AdvisorUnavailableError,
        JudgeUnavailableError,
        UnsafeEvalDatabaseError,
    ) as error:
        print(f"cannot run: {error}")
        return 2

    prompt_versions = {"advisor_system": SYSTEM_PROMPT.version}
    calibrated: frozenset[str] = frozenset()
    if judge is not None:
        prompt_versions["judge"] = judge.prompt_version
        state = load_calibration()
        calibrated = calibrated_rubrics(state, judge.model, judge.prompt_version)
        stale = [
            r.rubric
            for r in (state.rubrics if state else [])
            if r.calibrated and not r.matches(judge.model, judge.prompt_version)
        ]
        if stale:
            print(f"judge changed since the calibration of {stale}: they do not block")

    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    tracer = LangfuseTurnTracer(settings, run_id, model) if tracing_enabled(settings) else None
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            query = SqlProjectListingQuery(session)
            advisor = LangGraphAdvisor(
                chat_model=lambda: chat_model,
                model_name=model,
                tools=lambda: build_tools(query),
                # Memory per case run only: nothing reaches the database.
                checkpointer=InMemorySaver(),
                callbacks=langfuse_callbacks(settings),
                tags=["eval", run_id, model],
            )
            report = run_advisor_evals(
                cases,
                advisor,
                model=model,
                prompt_versions=prompt_versions,
                commit=git_commit(),
                repeat=args.repeat,
                cost_cap=CostCap(args.max_cost),
                judge=judge,
                calibrated=calibrated,
                tracer=tracer,
                known_numbers=tool_definition_numbers(build_tools(query)),
                run_id=run_id,
            )
    finally:
        engine.dispose()
        shutdown_tracing(settings)  # send the traces and scores before exiting
    return _write(report)


class LangfuseTurnTracer:
    """One Langfuse trace per turn, tagged with the run and the model, scored by the checks."""

    def __init__(self, settings: Settings, run_id: str, model: str) -> None:
        self._settings = settings
        self._tags = ["eval", run_id, model]

    def turn(
        self, *, case_id: str, run: int, turn: int, message: str, session_id: str
    ) -> AbstractContextManager[str | None]:
        """A span named after the case, run and turn; its session is the case run's thread."""
        return traced_span(
            self._settings,
            f"eval {case_id} r{run} t{turn}",
            input=message,
            session_id=session_id,
            tags=self._tags,
        )

    def score(self, trace_id: str | None, name: str, passed: bool, comment: str) -> None:
        """A BOOLEAN score on the turn's trace."""
        score_trace(self._settings, trace_id, name, passed, comment)


def _select(cases: list[EvalCase], ids: str | None) -> list[EvalCase]:
    if not ids:
        return cases
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    unknown = sorted(set(wanted) - {case.id for case in cases})
    if unknown:
        raise ValueError(f"unknown case ids: {unknown}")
    return [case for case in cases if case.id in wanted]


def _write(report: AdvisorRunReport) -> int:
    stem = report_stem("advisor", report.model, datetime.now(UTC).date())
    path = write_report(stem, report.model_dump_json(indent=2), report.to_markdown())
    print(report.to_markdown())
    print(f"report: {path} (and .md)")
    return 1 if report.failures() else 0


def _load_report(path: Path) -> AdvisorRunReport:
    return AdvisorRunReport.model_validate_json(path.read_text(encoding="utf-8"))


def _calibrate(args: argparse.Namespace) -> int:
    handlers = {
        "calibrate-add": _calibrate_add,
        "calibrate-sheet": _calibrate_sheet,
        "calibrate-import": _calibrate_import,
        "calibrate-judge": _calibrate_judge,
        "calibrate-score": _calibrate_score,
    }
    return handlers[args.command](args)


def _items(path: Path) -> list[LabelItem]:
    return load_items(path) if path.exists() else []


def _calibrate_add(args: argparse.Namespace) -> int:
    prompt = judge_prompt()
    new: list[LabelItem] = []
    if args.report is not None:
        report = _load_report(args.report)
        if report.judge_model is None:
            print(f"{args.report} was run with --no-judge: there is nothing to label")
            return 2
        rubrics = [r.strip() for r in args.rubrics.split(",") if r.strip()]
        new += export_for_labeling(report, prompt, rubrics)  # pyright: ignore[reportArgumentType]
    if not args.no_synthetic:
        new += load_synthetic(prompt, args.synthetic)
    existing = _items(args.labels)
    merged = add_new(existing, new)
    write_jsonl(args.labels, merged)
    print(f"{len(merged) - len(existing)} pairs added to {args.labels}; {len(merged)} in all")
    pending = sum(1 for item in merged if item.human_passed is None)
    print(f"{pending} without a label: run calibrate-sheet to label them")
    return 0


def _calibrate_sheet(args: argparse.Namespace) -> int:
    items = load_items(args.labels)
    sheet = render_sheet(items, args.seed)
    pending = sum(1 for item in items if item.human_passed is None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sheet, encoding="utf-8")
    print(f"{pending} pairs in {args.out}: write SI or NO after human_passed, then run")
    print(f"calibrate-import --sheet {args.out}")
    return 0


def _calibrate_import(args: argparse.Namespace) -> int:
    items = load_items(args.labels)
    answers = parse_sheet(args.sheet.read_text(encoding="utf-8"))
    unknown = sorted(set(answers) - {item.id for item in items})
    if unknown:
        print(f"the sheet has pairs that are not in {args.labels}: {unknown}")
        return 2
    updated, applied = apply_sheet(items, answers)
    write_jsonl(args.labels, updated)
    left = sum(1 for item in updated if item.human_passed is None)
    print(f"{applied} labels read from {args.sheet}; {left} pairs still without a label")
    return 0


def _calibrate_judge(args: argparse.Namespace) -> int:
    settings = load_settings()
    model = judge_model_name()
    try:
        require_prices([model], allow_unknown=args.allow_unknown_cost)
        judge = build_judge(settings, model, advisor_model=settings.advisor_model)
    except (JudgeUnavailableError, UnknownPriceError) as error:
        print(f"cannot judge: {error}")
        return 2
    items = load_items(args.labels)
    known = verdicts_of(load_verdicts(), judge.model, judge.prompt_version)
    todo = sum(1 for item in labeled(items) if item.id not in known)
    print(f"judging {todo} labeled pairs with {judge.model} (prompt {judge.prompt_version})")
    verdicts, usage, unjudged = judge_labeled(items, judge, known, CostCap(args.max_cost))
    append_verdicts(verdicts)
    print(f"{len(verdicts)} verdicts in {VERDICTS_PATH}, {usage.cost_usd:.4f} USD")
    for line in unjudged:
        print(f"not judged: {line}")
    return 1 if unjudged else 0


def _calibrate_score(args: argparse.Namespace) -> int:
    judge_model = judge_model_name()
    prompt_version = judge_prompt().version
    items = load_items(args.labels)
    verdicts = verdicts_of(load_verdicts(), judge_model, prompt_version)
    missing = sum(1 for item in labeled(items) if item.id not in verdicts)
    if missing:
        print(f"{missing} labeled pairs have no verdict from {judge_model} ({prompt_version}):")
        print("run calibrate-judge first")
        return 2
    agreements = score(items, verdicts, judge_model, prompt_version)
    if not agreements:
        print(f"no labeled pair in {args.labels}")
        return 2
    state = merge_calibration(load_calibration(), agreements, judge_model, prompt_version)
    save_calibration(state)
    print(to_markdown(agreements))
    calibrated = ", ".join(state.calibrated(judge_model, prompt_version)) or "none"
    print(f"calibrated with {judge_model} ({prompt_version}): {calibrated}")
    print(f"saved in {CALIBRATION_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
