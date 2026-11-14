"""Command line of the extraction evals: build, push, pull and run the golden set."""

import argparse
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from pydantic import ValidationError
from sqlalchemy.orm import Session

from sobreplano.evals.extraction.golden import (
    CACHE_DIR,
    PAGES_PATH,
    S3_PREFIX,
    ExtractionLabel,
    GoldenBuildError,
    build_case,
    load_cache,
    merge_labels,
    pull,
    push,
    read_pages,
    save_cache,
)
from sobreplano.evals.extraction.runner import run_extraction_evals
from sobreplano.evals.report import (
    CostCap,
    UnknownPriceError,
    git_commit,
    report_stem,
    require_prices,
    write_report,
)
from sobreplano.infrastructure.db.engine import create_db_engine
from sobreplano.infrastructure.llm.providers import build_extractor
from sobreplano.infrastructure.scraping.openai_compatible_extractor import UnavailableExtractor
from sobreplano.infrastructure.settings import load_settings
from sobreplano.interface.composition import SITES

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

DEFAULT_MAX_COST_USD = Decimal("0.10")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code (1 if the model is not eligible)."""
    parser = argparse.ArgumentParser(prog="python -m sobreplano.evals.extraction")
    commands = parser.add_subparsers(dest="command", required=True)
    bucket_help = "raw HTML bucket; default RAW_STORE (s3://bucket)"

    build_parser = commands.add_parser(
        "build", help="labels and texts from the cloud database and S3 (needs .env.cloud)"
    )
    build_parser.add_argument("--bucket", help=bucket_help)
    build_parser.add_argument("--pages", type=Path, default=PAGES_PATH)
    for name, text in (("push", "upload the local cache to S3"), ("pull", "download it from S3")):
        commands.add_parser(name, help=text).add_argument("--bucket", help=bucket_help)

    run_parser = commands.add_parser("run", help="run a model over the reviewed golden set")
    run_parser.add_argument("--model", help='"provider:model"; default EXTRACTION_MODEL')
    run_parser.add_argument("--repeat", type=int, default=1)
    run_parser.add_argument("--max-cost", type=Decimal, default=DEFAULT_MAX_COST_USD)
    run_parser.add_argument("--allow-unknown-cost", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run(args)
    bucket = args.bucket or _bucket_from_env()
    if bucket is None:
        print("pass --bucket or set RAW_STORE=s3://bucket")
        return 2
    s3: S3Client = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]
    if args.command == "push":
        print(f"uploaded {push(s3, bucket)} files to s3://{bucket}/{S3_PREFIX}")
        return 0
    if args.command == "pull":
        print(f"downloaded {pull(s3, bucket)} files into {CACHE_DIR}")
        return 0
    return _build(s3, bucket, args.pages)


def _bucket_from_env() -> str | None:
    raw_store = os.environ.get("RAW_STORE", "")
    return raw_store.removeprefix("s3://") if raw_store.startswith("s3://") else None


def _build(s3: "S3Client", bucket: str, pages: Path) -> int:
    existing, existing_texts = load_cache()
    labels: list[ExtractionLabel] = []
    texts: dict[str, str] = {}
    errors: list[str] = []
    engine = create_db_engine(null_pool=True)
    try:
        with Session(engine) as session:
            for url in read_pages(pages):
                try:
                    label, text = build_case(session, s3, bucket, SITES, url)
                except GoldenBuildError as error:
                    errors.append(str(error))
                    continue
                labels.append(label)
                texts[label.case_id] = text
    finally:
        engine.dispose()
    merged = merge_labels(existing, labels)
    kept = sum(1 for a, b in zip(merged, labels, strict=True) if a is not b)
    save_cache(merged, {**existing_texts, **texts})
    print(f"{len(merged)} labels in {CACHE_DIR} ({kept} reviewed labels kept)")
    for error in errors:
        print(f"skipped: {error}")
    print("review each label reading its text first, set reviewed: true, then push")
    return 1 if errors else 0


def _run(args: argparse.Namespace) -> int:
    if args.repeat < 1:
        print("--repeat must be at least 1")
        return 2
    settings = load_settings()
    if args.model:
        settings = settings.model_copy(update={"extraction_model": args.model})
    try:
        labels, texts = load_cache()
        require_prices([settings.extraction_model], allow_unknown=args.allow_unknown_cost)
        extractor = build_extractor(settings)
    except (OSError, ValidationError, ValueError, UnknownPriceError) as error:
        print(f"cannot run: {error}")
        return 2
    if not labels:
        print(f"no golden set in {CACHE_DIR}: run pull (or build) first")
        return 2
    if isinstance(extractor, UnavailableExtractor):
        print(f"cannot run: no API key for {settings.extraction_model}")
        return 2
    try:
        report = run_extraction_evals(
            labels,
            texts,
            extractor,
            commit=git_commit(),
            repeat=args.repeat,
            cost_cap=CostCap(args.max_cost),
        )
    except ValueError as error:
        print(f"cannot run: {error}")
        return 2
    stem = report_stem("extraction", report.model, datetime.now(UTC).date())
    path = write_report(stem, report.model_dump_json(indent=2), report.to_markdown())
    print(report.to_markdown())
    print(f"report: {path} (and .md)")
    return 1 if report.failures() else 0


if __name__ == "__main__":
    raise SystemExit(main())
