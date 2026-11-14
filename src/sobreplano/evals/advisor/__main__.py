"""Command line of the advisor evals: prepare the isolated database and run the cases."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.orm import Session

from sobreplano.domain.errors import AdvisorUnavailableError
from sobreplano.evals.advisor.cases import CASES_PATH, EvalCase, load_cases
from sobreplano.evals.advisor.database import (
    CATALOG_PATH,
    UnsafeEvalDatabaseError,
    check_local,
    eval_database_url,
    prepare,
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
from sobreplano.infrastructure.advisor.langgraph_advisor import LangGraphAdvisor
from sobreplano.infrastructure.advisor.tools import build_tools
from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery
from sobreplano.infrastructure.settings import load_settings

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
    args = parser.parse_args(argv)

    if args.command == "prepare":
        try:
            report = prepare(eval_database_url(), args.catalog)
        except UnsafeEvalDatabaseError as error:
            print(f"refusing to prepare: {error}")
            return 1
        print(report)
        return 0
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("--repeat must be at least 1")
        return 2
    settings = load_settings()
    if args.model:
        settings = settings.model_copy(update={"advisor_model": args.model})
    model: str = settings.advisor_model
    try:
        cases = _select(load_cases(args.cases_file), args.cases)
        require_prices([model], allow_unknown=args.allow_unknown_cost)
        chat_model = build_chat_model(settings)
        url = check_local(eval_database_url()).render_as_string(hide_password=False)
    except (
        ValueError,
        UnknownPriceError,
        AdvisorUnavailableError,
        UnsafeEvalDatabaseError,
    ) as error:
        print(f"cannot run: {error}")
        return 2

    engine = create_db_engine(url)
    try:
        with Session(engine) as session:
            advisor = LangGraphAdvisor(
                chat_model=lambda: chat_model,
                model_name=model,
                tools=build_tools(SqlProjectListingQuery(session)),
                # Memory per case run only: nothing reaches the database.
                checkpointer=InMemorySaver(),
            )
            report = run_advisor_evals(
                cases,
                advisor,
                model=model,
                prompt_versions={"advisor_system": SYSTEM_PROMPT.version},
                commit=git_commit(),
                repeat=args.repeat,
                cost_cap=CostCap(args.max_cost),
            )
    finally:
        engine.dispose()
    return _write(report)


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


if __name__ == "__main__":
    raise SystemExit(main())
