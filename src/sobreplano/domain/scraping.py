"""Scraping entities: runs, fetched pages and extraction results."""

from enum import StrEnum


class ScrapeRunStatus(StrEnum):
    """Lifecycle of one scrape run of one developer."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
