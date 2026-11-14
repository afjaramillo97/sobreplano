"""Command line of the advisor evals: prepare the isolated database (more commands later)."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from sobreplano.evals.advisor.database import (
    CATALOG_PATH,
    UnsafeEvalDatabaseError,
    eval_database_url,
    prepare,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="python -m sobreplano.evals.advisor")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser(
        "prepare", help="recreate the evals database (EVAL_DATABASE_URL) and load the catalog"
    )
    prepare_parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    args = parser.parse_args(argv)

    if args.command == "prepare":
        try:
            report = prepare(eval_database_url(), args.catalog)
        except UnsafeEvalDatabaseError as error:
            print(f"refusing to prepare: {error}")
            return 1
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
