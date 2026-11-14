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
    TO_LABEL_PATH,
    CalibrationState,
    calibrated_rubrics,
    export_for_labeling,
    load_calibration,
    load_labels,
    save_calibration,
    score,
    to_markdown,
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
from sobreplano.evals.advisor.runner import (
    AdvisorRunReport,
    run_advisor_evals,
    tool_definition_numbers,
)
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

    export_parser = commands.add_parser(
        "calibrate-export", help="write the judged pairs of a report to label, without verdicts"
    )
    export_parser.add_argument("--report", type=Path, required=True)
    export_parser.add_argument("--out", type=Path, default=TO_LABEL_PATH)

    score_parser = commands.add_parser(
        "calibrate-score", help="compare labels with a report's verdicts and save calibration"
    )
    score_parser.add_argument("--report", type=Path, required=True)
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
    try:
        if args.command == "calibrate-export":
            return _calibrate_export(args.report, args.out)
        if args.command == "calibrate-score":
            return _calibrate_score(args.report, args.labels)
    except (OSError, ValidationError) as error:
        print(f"cannot read {args.report} or the labels: {error}")
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
        calibrated = calibrated_rubrics(state, judge.prompt_version)
        if state is not None and state.judge_prompt_version != judge.prompt_version:
            print("judge prompt changed since calibration: no rubric blocks until recalibrated")

    run_id = f"run-{datetime.now(UTC):%Y%m%dT%H%M%S}"
    tracer = LangfuseTurnTracer(settings, run_id, model) if tracing_enabled(settings) else None
    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            tools = build_tools(SqlProjectListingQuery(session))
            advisor = LangGraphAdvisor(
                chat_model=lambda: chat_model,
                model_name=model,
                tools=tools,
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
                known_numbers=tool_definition_numbers(tools),
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


def _calibrate_export(report_path: Path, out: Path) -> int:
    report = _load_report(report_path)
    if report.judge_model is None:
        print(f"{report_path} was run with --no-judge: there is nothing to label")
        return 2
    count = write_jsonl(out, export_for_labeling(report, judge_prompt()))
    print(f"{count} pairs to label in {out}: fill human_passed (true/false), then save the")
    print(f"labeled lines in {LABELS_PATH} and run calibrate-score --report {report_path}")
    return 0


def _calibrate_score(report_path: Path, labels_path: Path) -> int:
    report = _load_report(report_path)
    prompt = judge_prompt()
    if report.prompt_versions.get("judge") != prompt.version:
        print("the report was judged with another judge prompt: run the evals again first")
        return 2
    agreements = score(report, load_labels(labels_path))
    if not agreements:
        print(f"no labeled pair of {labels_path} matches {report_path}")
        return 2
    state = CalibrationState(
        judge_model=report.judge_model or "",
        judge_prompt_version=prompt.version,
        report=report_path.name,
        rubrics=agreements,
    )
    save_calibration(state)
    print(to_markdown(agreements))
    print(f"calibrated: {', '.join(state.calibrated()) or 'none'} (saved in {CALIBRATION_PATH})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
