"""Scrape one developer's site once: python -m sobreplano.interface.cli.scrape londono-gomez."""

import argparse
import logging
from collections.abc import Sequence

from pydantic import ValidationError

from sobreplano.domain.scraping import ScrapeRunStatus
from sobreplano.infrastructure.settings import load_settings
from sobreplano.interface.composition import (
    SITES,
    ConfigurationError,
    format_summary,
    run_scrape,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; exits 0 when the run succeeds, 1 when it fails, 2 on bad configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("developer", choices=sorted(SITES))
    parser.add_argument("--limit", type=int, default=None, help="at most N project pages")
    parser.add_argument(
        "--dry-run", action="store_true", help="fetch and extract, then roll the database back"
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # One line per HTTP request from httpx and openai is noise next to the run's own log.
    for noisy in ("httpx", "httpx2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    try:
        settings = load_settings()
        report = run_scrape(settings, args.developer, limit=args.limit, dry_run=args.dry_run)
    except (ValidationError, ConfigurationError) as error:
        print(f"bad configuration: {error}")
        return 2

    print(format_summary(report, settings.extraction_model, dry_run=args.dry_run))
    return 0 if report.status is ScrapeRunStatus.SUCCEEDED else 1


if __name__ == "__main__":
    raise SystemExit(main())
